import XCTest
import Yams
@testable import Jetlag

/// Stands in for the scripts: each launch replays the lines recorded for that
/// script, then ends, and the scripts launched are recorded in order.
final class ReplayingLauncher: ScriptLaunching {
    private let output: [String: [LogLine]]
    private(set) var launched: [String] = []

    init(_ output: [String: [LogLine]]) {
        self.output = output
    }

    func run(script: String, args: [String]) -> (process: ScriptProcess, stream: AsyncStream<LogLine>) {
        launched.append(script)
        let lines = output[script] ?? []
        let stream = AsyncStream<LogLine> { continuation in
            for line in lines {
                continuation.yield(line)
            }
            continuation.finish()
        }
        return (ScriptProcess(processIdentifier: -1), stream)
    }
}

/// A run end to end inside the app, with no script spawned: Run, the media count
/// checked against the free tier, the pipeline launch, every JSONL line folded
/// into the table and the summary, and the popup or alert raised at the end.
/// The pipeline's output is the schema's own example events
/// (scripts/pipeline-schema.yaml), so the run is fed exactly what the contract
/// says the pipeline emits.
final class ScriptedRunTests: XCTestCase {

    private static let schemaURL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()   // Tests
        .deletingLastPathComponent()   // macos
        .deletingLastPathComponent()   // repo root
        .appendingPathComponent("scripts/pipeline-schema.yaml")

    private static let file = "DJI_20250815_101112_0001.MP4"

    /// An interpreter is always there to run the scripts on.
    private let pythonReady = PythonRuntimeCheck(
        developerDirectoryPresent: { true },
        overrideInterpreter: { nil },
        pathInterpreter: { nil })

    /// The schema's example for `event`, as the single stdout line the pipeline
    /// would write for it.
    private func example(_ event: String) throws -> LogLine {
        let text = try String(contentsOf: Self.schemaURL, encoding: .utf8)
        let root = try XCTUnwrap(try Yams.load(yaml: text) as? [String: Any])
        let events = try XCTUnwrap(root["events"] as? [String: [String: Any]])
        let instance = try XCTUnwrap(events[event]?["example"] as? [String: Any],
                                     "\(event) has no example")
        let data = try JSONSerialization.data(withJSONObject: instance)
        return LogLine(text: try XCTUnwrap(String(data: data, encoding: .utf8)), stream: .stdout)
    }

    private func countLine(_ count: Int) -> LogLine {
        LogLine(text: "{\"media_files\": \(count)}", stream: .stdout)
    }

    /// A state on the free tier, with a profile picked whose source holds media.
    private func makeState(launcher: ReplayingLauncher) -> AppState {
        let suiteName = "ScriptedRunTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        addTeardownBlock { defaults.removePersistentDomain(forName: suiteName) }
        let store = LicenseStore(defaults: defaults, environment: [:], developerBuild: false)
        let state = AppState(launcher: launcher, licenseStore: store)
        state.workflowSession = WorkflowSession(
            profile: MediaProfile(type: .video, sourceDir: "/Volumes/SD/DCIM",
                                  readyDir: "/Volumes/Media/Ready", fileExtensions: [".mp4"]),
            profileName: "dji")
        return state
    }

    /// Press Run and wait for the run to end: first the media count, then the
    /// pipeline the count started. Run is pressed on the main actor, as in the
    /// app: the replayed count answers at once, and only a busy main actor keeps
    /// the count's task from starting the pipeline before Run has stored it.
    @MainActor
    private func runToCompletion(_ state: AppState) async {
        state.runWorkflow(check: pythonReady)
        await state.currentRunTask?.value
        let pipeline = state.currentRunTask
        await pipeline?.value
    }

    /// One file through every stage: its events become one finished row, the
    /// summary event becomes the popup, and no JSON reaches the log.
    func testARunFoldsThePipelinesEventsIntoRowsAndTheSummary() async throws {
        let progress = LogLine(text: "📁 Organizing by date...", stream: .stderr)
        let launcher = ReplayingLauncher([
            "scan-source.sh": [countLine(1)],
            "media-pipeline.sh": [
                try example("pipeline_file"),
                try example("tag_result"),
                try example("timestamp_result"),
                try example("stage_complete"),
                progress,
                try example("organize_result"),
                try example("pipeline_result"),
                try example("pipeline_summary"),
            ],
        ])
        let state = makeState(launcher: launcher)

        await runToCompletion(state)

        XCTAssertEqual(launcher.launched, ["scan-source.sh", "media-pipeline.sh"])
        XCTAssertEqual(state.diffTableRows.count, 1)
        let row = try XCTUnwrap(state.diffTableRows.first)
        XCTAssertEqual(row.file, Self.file)
        XCTAssertEqual(row.sourcePath, "/Volumes/SD/DCIM/100GOPRO/\(Self.file)")
        XCTAssertEqual(row.tagAction, "tagged")
        XCTAssertEqual(row.timestampAction, "would_fix")
        XCTAssertEqual(row.organizeAction, "skipped")
        XCTAssertEqual(row.organizeReason, "exists_differs")
        XCTAssertEqual(row.dest, "/Volumes/Media/Ready/2025/2025-08-15/\(Self.file)")
        XCTAssertEqual(row.pipelineResult, "would_change")
        XCTAssertEqual(state.visibleRows.count, 1, "no row is left in progress")

        XCTAssertEqual(state.runSummary, PipelineSummary(
            processed: 2, succeeded: 1, changed: 1, failed: 1,
            failedFiles: [Self.file], mode: .applied))
        XCTAssertTrue(state.showRunSummary)
        XCTAssertFalse(state.isRunning)

        XCTAssertEqual(state.logOutput.map(\.text), [progress.text])
    }

    /// A count over the free tier's limit asks to upgrade and never launches the
    /// pipeline.
    func testARunOverTheFreeTierLimitLaunchesNothing() async {
        let launcher = ReplayingLauncher(["scan-source.sh": [countLine(51)]])
        let state = makeState(launcher: launcher)

        await runToCompletion(state)

        XCTAssertEqual(launcher.launched, ["scan-source.sh"])
        XCTAssertEqual(state.upgradePrompt?.fileCount, 51)
        XCTAssertFalse(state.isRunning)
        XCTAssertTrue(state.diffTableRows.isEmpty)
    }

    /// An apply the pipeline refuses for a zone mismatch asks the user, and
    /// answering re-runs it as the apply it was.
    func testAnApplyRefusedForAZoneMismatchAsks() async throws {
        let launcher = ReplayingLauncher([
            "scan-source.sh": [countLine(1)],
            "media-pipeline.sh": [try example("timezone_conflict")],
        ])
        let state = makeState(launcher: launcher)
        state.workflowSession.applyMode = true
        state.workflowSession.applyWithoutDryRun = true

        await runToCompletion(state)

        XCTAssertTrue(state.workflowSession.showTimezoneConflict)
        XCTAssertEqual(state.workflowSession.timezoneConflictProvidedTz, "+09:00")
        XCTAssertNil(state.runSummary, "a refused run reports no summary")
        XCTAssertFalse(state.showRunSummary)

        state.workflowSession.grantTimezoneAssent()
        XCTAssertTrue(state.workflowSession.applyMode)
        XCTAssertTrue(state.workflowSession.buildPipelineArgs().args.contains(WorkflowSession.forceTimezoneFlag))
    }
}
