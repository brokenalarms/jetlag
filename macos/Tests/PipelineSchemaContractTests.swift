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
/// Command line: `PipelineStep`'s cases and tokens, and every flag the app passes,
/// have to be the ones the schema's `cli` section declares — the section
/// media-pipeline's parser is held to on the Python side.
final class PipelineSchemaContractTests: XCTestCase {

    private static let schemaURL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()   // Tests
        .deletingLastPathComponent()   // macos
        .deletingLastPathComponent()   // repo root
        .appendingPathComponent("scripts/lib/media_pipeline/pipeline-schema.yaml")

    private func schema() throws -> [String: [String: Any]] {
        let text = try String(contentsOf: Self.schemaURL, encoding: .utf8)
        let root = try Yams.load(yaml: text) as? [String: Any]
        let events = try XCTUnwrap(root?["events"] as? [String: [String: Any]],
                                   "pipeline-schema.yaml has no events mapping")
        return events
    }

    private func cli() throws -> [String: Any] {
        let text = try String(contentsOf: Self.schemaURL, encoding: .utf8)
        let root = try Yams.load(yaml: text) as? [String: Any]
        return try XCTUnwrap(root?["cli"] as? [String: Any], "pipeline-schema.yaml has no cli mapping")
    }

    private func cliSteps() throws -> [[String: Any]] {
        try XCTUnwrap(cli()["steps"] as? [[String: Any]], "pipeline-schema.yaml declares no cli.steps")
    }

    private func cliList(_ key: String) throws -> [String] {
        try XCTUnwrap(cli()[key] as? [String], "pipeline-schema.yaml declares no cli.\(key)")
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
        case .pipelineSummary: return "pipeline_summary"
        case .timezoneConflict: return "timezone_conflict"
        case .organizeConflict: return "organize_conflict"
        case .protectedSources: return "protected_sources"
        case .cameraMismatch: return "camera_mismatch"
        case .noMediaFiles: return "no_media_files"
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

    /// `.skipped`'s label also depends on `organize_result.reason` and whether the
    /// pipeline is in a dry run, so its grid is exhaustive over every reason token
    /// and both dry-run states; every other action ignores both.
    func testEveryOrganizeActionTokenHasAStatusLabel() throws {
        let declaredActions = try tokens(schema(), event: "organize_result", field: "action")
        let declaredReasons = try tokens(schema(), event: "organize_result", field: "reason")

        for token in declaredActions {
            let movement = RowOutcome.Movement(rawValue: token)
            XCTAssertNotNil(movement, "organize_result.action '\(token)' has no case in RowOutcome.Movement")
            guard let movement else { continue }

            guard movement == .skipped else {
                XCTAssertFalse(movement.statusLabel(reason: nil, dryRun: false).isEmpty,
                               "organize_result.action '\(token)' has no status label")
                XCTAssertFalse(movement.statusLabelAfterCorrection(reason: nil, dryRun: false).isEmpty,
                               "organize_result.action '\(token)' has no combined status label")
                continue
            }

            for reasonToken in declaredReasons {
                let reason = RowOutcome.SkipReason(rawValue: reasonToken)
                XCTAssertNotNil(reason, "organize_result.reason '\(reasonToken)' has no case in RowOutcome.SkipReason")
                for dryRun in [true, false] {
                    XCTAssertFalse(movement.statusLabel(reason: reason, dryRun: dryRun).isEmpty,
                                   "skipped/\(reasonToken) (dryRun=\(dryRun)) has no status label")
                    XCTAssertFalse(movement.statusLabelAfterCorrection(reason: reason, dryRun: dryRun).isEmpty,
                                   "skipped/\(reasonToken) (dryRun=\(dryRun)) has no combined status label")
                }
            }
        }

        XCTAssertEqual(Set(RowOutcome.Movement.allCases.map(\.rawValue)), declaredActions,
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

    /// The table's status badge switches over these with no default, so a verdict
    /// the schema adds has to be given a status here.
    func testEveryPipelineResultTokenIsAKnownFileResult() throws {
        let declared = try tokens(schema(), event: "pipeline_result", field: "result")

        XCTAssertEqual(Set(RowOutcome.FileResult.allCases.map(\.rawValue)), declared,
                       "RowOutcome.FileResult and pipeline_result.result have drifted apart")
    }

    /// Which flag answers a refused run depends on the conflict, so every kind the
    /// pipeline can report has to decode into one the app knows.
    func testEveryTimezoneConflictTypeIsAKnownKind() throws {
        let declared = try tokens(schema(), event: "timezone_conflict", field: "conflict_type")

        XCTAssertEqual(Set(TimezoneConflictKind.allCases.map(\.rawValue)), declared,
                       "TimezoneConflictKind and timezone_conflict.conflict_type have drifted apart")
    }

    /// The step list is the pipeline's, in its order: a row's progress label picks
    /// the last stage it finished by this order, and `--tasks` is built from it.
    func testPipelineStepsAreTheDeclaredStepsInPipelineOrder() throws {
        let steps = try cliSteps()

        XCTAssertEqual(PipelineStep.allCases.map(\.stageToken), steps.compactMap { $0["stage"] as? String },
                       "PipelineStep and cli.steps have drifted apart (stage tokens or order)")
        XCTAssertEqual(PipelineStep.allCases.map(\.taskToken), steps.map { $0["task"] as? String },
                       "PipelineStep.taskToken and cli.steps' task tokens have drifted apart")
        XCTAssertEqual(PipelineStep.allCases.map(\.isAlwaysOn), steps.map { $0["task"] == nil },
                       "A step that always runs is exactly one --tasks cannot name")
    }

    /// The stage_complete tokens the app can label are the ones the pipeline emits.
    func testEveryStageCompleteTokenIsAPipelineStep() throws {
        let declared = try tokens(schema(), event: "stage_complete", field: "stage")

        XCTAssertEqual(Set(PipelineStep.allCases.map(\.stageToken)), declared,
                       "PipelineStep.stageToken and stage_complete.stage have drifted apart")
    }

    /// The flags a fully configured run passes — every step on, every option set,
    /// every answer given — are exactly the ones media-pipeline's parser is held to.
    func testEveryFlagTheAppPassesIsDeclared() throws {
        var profile = MediaProfile(
            type: .video, sourceDir: "/Volumes/TestCard/DCIM", readyDir: "/tmp/ready",
            gyroflowEnabled: true, fileExtensions: [".mp4"]
        )
        profile.tags = ["travel"]
        profile.exif = ExifConfig(make: "DJI", model: "Osmo Action 4")
        profile.gyroflowSettings = StabilizationSettings(maxZoom: 110.0)
        let session = WorkflowSession(profile: profile, profileName: "test-profile", gyroflowAvailable: true)
        session.enabledSteps = Set(session.availableSteps)
        session.timezone.value = "Asia/Tokyo"
        session.group = "Japan"
        session.copyCompanionFiles = true
        session.inferFromFilenames = true
        session.timeOffsetSeconds = 3600
        session.updateFilenameDates = true
        session.forceTimezone = true
        session.allowMixedTimezones = true
        session.overwriteDestination = true
        session.unlockProtected = true
        session.allowCameraMismatch = true
        session.applyMode = true

        let declared = try cliList("flags")
        let passed = session.buildPipelineArgs().args.filter { $0.hasPrefix("--") }

        XCTAssertEqual(Set(passed), Set(declared),
                       "The flags the app passes and cli.flags have drifted apart")
    }

    /// The flags dropped from the dry-run comparison are the schema's assent flags:
    /// an answer for one run never makes a preview look stale.
    func testAssentFlagsAreTheDeclaredOnes() throws {
        let declared = try cliList("assent_flags")

        XCTAssertEqual(Set(WorkflowSession.assentFlags), Set(declared),
                       "WorkflowSession.assentFlags and cli.assent_flags have drifted apart")
    }

    /// The mapping is 1:1: two tokens sharing a label would mean the app decides an
    /// outcome the script already named. Lumping copied, moved and overwrote into
    /// "Moved" is exactly what told the user a pipelined file had left its folder.
    func testNoTwoOrganizeActionTokensShareALabel() throws {
        let declaredActions = try tokens(schema(), event: "organize_result", field: "action")

        var labels: [String: String] = [:]
        var combined: [String: String] = [:]
        for token in declaredActions {
            let movement = try XCTUnwrap(RowOutcome.Movement(rawValue: token))
            let label = movement.statusLabel(reason: nil, dryRun: false)
            let afterFix = movement.statusLabelAfterCorrection(reason: nil, dryRun: false)
            XCTAssertNil(labels[label],
                         "'\(token)' and '\(labels[label] ?? "")' both render as '\(label)'")
            XCTAssertNil(combined[afterFix],
                         "'\(token)' and '\(combined[afterFix] ?? "")' both render as '\(afterFix)'")
            labels[label] = token
            combined[afterFix] = token
        }
    }

    /// The app renders the token and consults nothing else. Anything the row knows
    /// about the working directory or the ingest step would be the app re-deriving
    /// an outcome the script already decided — the bug this whole contract exists
    /// to prevent, one layer up from `dest`.
    func testStatusRenderingNamesNoStagingState() throws {
        let sources = ["Sources/Models/RowOutcome.swift", "Sources/Views/DiffTableView.swift"]
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // Tests
            .deletingLastPathComponent()   // macos

        for source in sources {
            let text = try String(contentsOf: root.appendingPathComponent(source), encoding: .utf8)
            for term in ["ingest", "workingDir", "working_dir", "working directory"] {
                XCTAssertFalse(text.lowercased().contains(term.lowercased()),
                               "\(source) mentions '\(term)' — the outcome comes from the token alone")
            }
        }
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

    /// A dry run's destination conflict never reads as a move — but it also must not
    /// read as "skipped": Apply prompts and, on assent, moves and replaces. jetlag-bjt.
    func testSkippedMoveNeverReadsAsAMove() {
        let skipped = row(timestamp: "would_fix", organize: "skipped",
                          reason: "exists_differs",
                          dest: "/Volumes/Media/Ready/2025/2025-08-15/DJI_0001.MP4",
                          result: "would_change")

        let label = skipped.outcome.statusLabel

        XCTAssertEqual(label, Strings.DiffTable.combinedStatus(
            Strings.DiffTable.wouldFixStatus, Strings.DiffTable.wouldReplaceStatusAfterFix))
        XCTAssertNotEqual(label, Strings.DiffTable.combinedStatus(
            Strings.DiffTable.wouldFixStatus, Strings.DiffTable.wouldMoveStatusAfterFix))
        XCTAssertNotEqual(label, Strings.DiffTable.combinedStatus(
            Strings.DiffTable.wouldFixStatus, Strings.DiffTable.moveSkippedStatusAfterFix))
    }

    /// The other skip reason a dry run can report: nothing to apply, so it reads as
    /// a fact ("destination already has it") rather than a pending action.
    func testSkippedIdenticalInDryRunNeedsNoMove() {
        let identical = row(timestamp: "would_fix", organize: "skipped",
                            reason: "identical",
                            dest: "/Volumes/Media/Ready/2025/2025-08-15/DJI_0001.MP4",
                            result: "would_change")

        XCTAssertEqual(identical.outcome.statusLabel,
                       Strings.DiffTable.wouldFixIdenticalStatus(Strings.DiffTable.wouldFixStatus))
    }

    /// An applied run's destination conflict keeps "move skipped" — the prompt
    /// already happened and the user chose not to overwrite, so nothing was moved.
    func testAppliedSkippedKeepsMoveSkippedLabel() {
        let applied = row(timestamp: "fixed", organize: "skipped",
                          reason: "exists_differs",
                          dest: "/Volumes/Media/Ready/2025/2025-08-15/DJI_0001.MP4",
                          result: "changed")

        XCTAssertEqual(applied.outcome.statusLabel, Strings.DiffTable.combinedStatus(
            Strings.DiffTable.fixedStatus, Strings.DiffTable.moveSkippedStatusAfterFix))
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

    /// A row that only gains missing fields keeps its own wording when combined with
    /// its organize outcome, rather than reading as "Would fix + copy".
    func testPlannedAdditionReadsAsAddingMetadataNotAFix() {
        let planned = row(timestamp: "would_add", organize: "would_copy",
                          dest: "/Volumes/Media/Ready/2026/2026-10-28/C0307.MP4",
                          result: "would_change")

        let label = planned.outcome.statusLabel

        XCTAssertEqual(label, Strings.DiffTable.combinedStatus(
            Strings.DiffTable.wouldAddStatus, Strings.DiffTable.wouldCopyStatusAfterFix))
        XCTAssertNotEqual(label, Strings.DiffTable.combinedStatus(
            Strings.DiffTable.wouldFixStatus, Strings.DiffTable.wouldCopyStatusAfterFix))
    }

    func testAppliedRunReportsWhatWasDone() {
        let applied = row(timestamp: "fixed", organize: "moved",
                          dest: "/Volumes/Media/Ready/2025/2025-08-15/DJI_0001.MP4",
                          result: "changed")

        XCTAssertEqual(applied.outcome.statusLabel, Strings.DiffTable.combinedStatus(
            Strings.DiffTable.fixedStatus, Strings.DiffTable.movedStatusAfterFix))
    }

    /// The pipeline stages every file, so what it reports is a copy: a new file at
    /// the destination with the source left where it was. The row has to say so
    /// rather than borrow the move wording. jetlag-wn7.
    func testCopiedReadsAsACopyNotAMove() {
        let applied = row(timestamp: "fixed", organize: "copied",
                          dest: "/Volumes/Media/Ready/2025/2025-08-15/DJI_0001.MP4",
                          result: "changed")

        let label = applied.outcome.statusLabel

        XCTAssertEqual(label, Strings.DiffTable.combinedStatus(
            Strings.DiffTable.fixedStatus, Strings.DiffTable.copiedStatusAfterFix))
        XCTAssertNotEqual(label, Strings.DiffTable.combinedStatus(
            Strings.DiffTable.fixedStatus, Strings.DiffTable.movedStatusAfterFix))
    }

    /// The dry run previews the same copy the apply above performs, so its wording
    /// has to match — a preview that says "move" describes a different run.
    func testWouldCopyReadsAsACopyNotAMove() {
        let planned = row(timestamp: "would_fix", organize: "would_copy",
                          dest: "/Volumes/Media/Ready/2025/2025-08-15/DJI_0001.MP4",
                          result: "would_change")

        let label = planned.outcome.statusLabel

        XCTAssertEqual(label, Strings.DiffTable.combinedStatus(
            Strings.DiffTable.wouldFixStatus, Strings.DiffTable.wouldCopyStatusAfterFix))
        XCTAssertNotEqual(label, Strings.DiffTable.combinedStatus(
            Strings.DiffTable.wouldFixStatus, Strings.DiffTable.wouldMoveStatusAfterFix))
    }

    func testCopyWithoutACorrectionStandsAlone() {
        let copiedOnly = row(timestamp: "no_change", organize: "copied",
                             dest: "/Volumes/Media/Ready/2025/2025-08-15/DJI_0001.MP4",
                             result: "changed")

        XCTAssertEqual(copiedOnly.outcome.statusLabel, Strings.DiffTable.copiedStatus)
        XCTAssertNotEqual(copiedOnly.outcome.statusLabel, Strings.DiffTable.movedStatus)
    }

    /// A replacement is neither a plain copy nor a move: something that was at the
    /// destination is gone, which is the part the user needs told.
    func testOverwroteReadsAsAReplacement() {
        let replaced = row(timestamp: "no_change", organize: "overwrote",
                           dest: "/Volumes/Media/Ready/2025/2025-08-15/DJI_0001.MP4",
                           result: "changed")

        XCTAssertEqual(replaced.outcome.statusLabel, Strings.DiffTable.overwroteStatus)
        XCTAssertNotEqual(replaced.outcome.statusLabel, Strings.DiffTable.copiedStatus)
        XCTAssertNotEqual(replaced.outcome.statusLabel, Strings.DiffTable.movedStatus)
    }

    /// End to end from the wire: a copied event carries copy wording all the way to
    /// the row, so nothing between the script and the table reinterprets the token.
    func testCopiedOrganizeEventReachesTheRowAsACopy() {
        let state = AppState()

        state.appendLog(LogLine(text: #"{"event": "pipeline_file", "file": "DJI_0001.MP4"}"#,
                                stream: .stdout))
        state.appendLog(LogLine(text: """
        {"event": "organize_result", "file": "DJI_0001.MP4", "action": "copied", \
        "dest": "/Volumes/Media/Ready/2025/2025-08-15/DJI_0001.MP4"}
        """, stream: .stdout))
        state.appendLog(LogLine(
            text: #"{"event": "pipeline_result", "file": "DJI_0001.MP4", "result": "changed"}"#,
            stream: .stdout))

        XCTAssertEqual(state.diffTableRows.count, 1)
        let row = state.diffTableRows[0]
        XCTAssertEqual(row.organizeAction, "copied")
        XCTAssertNil(row.skipReason, "A copied file has no skip reason to show")
        XCTAssertEqual(row.outcome.statusLabel, Strings.DiffTable.copiedStatus)
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
            Strings.DiffTable.wouldFixStatus, Strings.DiffTable.wouldReplaceStatusAfterFix))
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
