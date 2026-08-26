import XCTest
@testable import Jetlag

final class AppStateTests: XCTestCase {

    func testClearLogPreservesLogVisibility() {
        let state = AppState()
        state.showLogOutput = true
        state.logOutput = [LogLine(text: "hello", stream: .stdout)]

        state.clearLog()

        XCTAssertTrue(state.showLogOutput)
        XCTAssertTrue(state.logOutput.isEmpty)
    }

    func testClearLogPreservesInspector() {
        let state = AppState()
        state.showInspector = true
        state.logOutput = [LogLine(text: "hello", stream: .stdout)]

        state.clearLog()

        XCTAssertTrue(state.showInspector)
        XCTAssertTrue(state.logOutput.isEmpty)
        XCTAssertTrue(state.diffTableRows.isEmpty)
    }

    func testNavigateToProfilesClearsAll() {
        let state = AppState()
        state.showLogOutput = true
        state.showInspector = true
        state.logOutput = [LogLine(text: "hello", stream: .stdout)]

        state.selectedTab = .profiles

        XCTAssertFalse(state.showLogOutput)
        XCTAssertFalse(state.showInspector)
        XCTAssertTrue(state.logOutput.isEmpty)
        XCTAssertTrue(state.diffTableRows.isEmpty)
    }

    func testNavigateBackToWorkflowPreservesCleanState() {
        let state = AppState()
        state.showLogOutput = true
        state.showInspector = true
        state.logOutput = [LogLine(text: "hello", stream: .stdout)]

        state.selectedTab = .profiles
        state.selectedTab = .workflow

        XCTAssertFalse(state.showLogOutput)
        XCTAssertFalse(state.showInspector)
        XCTAssertTrue(state.logOutput.isEmpty)
        XCTAssertTrue(state.diffTableRows.isEmpty)
    }
}

/// Covers how the app reacts to the pipeline's timezone-conflict reporting:
/// a dry-run preview flags the affected rows quietly, while applying is what
/// prompts the user to confirm the relabel.
final class TimezoneConflictTests: XCTestCase {

    private func feed(_ state: AppState, _ json: String) {
        state.appendLog(LogLine(text: json, stream: .stdout))
    }

    private func feedConflict(_ state: AppState, type: String) {
        feed(state, """
        {"event": "timezone_conflict", "conflict_type": "\(type)", \
        "provided_tz": "+0200", "file_timezones": {"+0900": ["test.mp4"]}}
        """)
    }

    /// A preview row whose file already carries a camera-set zone is flagged in
    /// the diff table, so the user can see which files the relabel would touch.
    func testRequiresForceTimezoneReachesTheDiffTableRow() {
        let state = AppState()

        feed(state, #"{"event": "pipeline_file", "file": "test.mp4"}"#)
        feed(state, """
        {"event": "timestamp_result", "file": "test.mp4", "action": "would_fix", \
        "original_time": "2025:10:05 01:00:00+09:00", "corrected_time": "2025:10:04 18:00:00+02:00", \
        "requires_force_timezone": true}
        """)
        feed(state, #"{"event": "pipeline_result", "file": "test.mp4", "result": "would_change"}"#)

        XCTAssertEqual(state.diffTableRows.count, 1)
        XCTAssertTrue(state.diffTableRows[0].requiresForceTimezone)
    }

    /// Files that need no relabel are not flagged, so the warning stays meaningful.
    func testUnflaggedRowsStayUnflagged() {
        let state = AppState()

        feed(state, #"{"event": "pipeline_file", "file": "test.mp4"}"#)
        feed(state, """
        {"event": "timestamp_result", "file": "test.mp4", "action": "would_fix", \
        "original_time": "2025:10:05 01:00:00", "corrected_time": "2025:10:05 01:00:00+02:00"}
        """)
        feed(state, #"{"event": "pipeline_result", "file": "test.mp4", "result": "would_change"}"#)

        XCTAssertEqual(state.diffTableRows.count, 1)
        XCTAssertFalse(state.diffTableRows[0].requiresForceTimezone)
    }

    /// The winning source and the fields a correction would write reach the row, so
    /// the table can explain a "Would fix" whose original and corrected times are the
    /// same string — here a stale movie header with no Keys:CreationDate.
    func testSourceAndStaleFieldsReachTheDiffTableRow() {
        let state = AppState()

        feed(state, #"{"event": "pipeline_file", "file": "test.mp4"}"#)
        feed(state, """
        {"event": "timestamp_result", "file": "test.mp4", "action": "would_fix", \
        "original_time": "2025:08:15 14:08:51+09:00", "corrected_time": "2025:08:15 14:08:51+09:00", \
        "source": "datetimeoriginal", \
        "stale_fields": ["Keys:CreationDate", "QuickTime:CreateDate"]}
        """)
        feed(state, #"{"event": "pipeline_result", "file": "test.mp4", "result": "would_change"}"#)

        XCTAssertEqual(state.diffTableRows.count, 1)
        XCTAssertEqual(state.diffTableRows[0].timestampSource, .dateTimeOriginal)
        XCTAssertEqual(state.diffTableRows[0].staleFields,
                       ["Keys:CreationDate", "QuickTime:CreateDate"])
    }

    /// A result that names no fields leaves the row's list empty rather than absent,
    /// and an unrecognised source token leaves the row without one.
    func testMissingSourceAndStaleFieldsLeaveTheRowEmpty() {
        let state = AppState()

        feed(state, #"{"event": "pipeline_file", "file": "test.mp4"}"#)
        feed(state, """
        {"event": "timestamp_result", "file": "test.mp4", "action": "no_change", \
        "original_time": "2025:08:15 14:08:51+09:00", "corrected_time": "2025:08:15 14:08:51+09:00"}
        """)
        feed(state, #"{"event": "pipeline_result", "file": "test.mp4", "result": "unchanged"}"#)

        XCTAssertEqual(state.diffTableRows.count, 1)
        XCTAssertNil(state.diffTableRows[0].timestampSource)
        XCTAssertEqual(state.diffTableRows[0].staleFields, [])
    }

    /// A UTC-clock row shows its original as UTC while its corrected time keeps the
    /// declared zone — the nine-hour gap between the two columns is a relabel, and
    /// the row now says so.
    func testUTCClockRowRendersItsOriginalAsUTC() {
        let state = AppState()

        feed(state, #"{"event": "pipeline_file", "file": "test.mp4"}"#)
        feed(state, """
        {"event": "timestamp_result", "file": "test.mp4", "action": "would_fix", \
        "original_time": "2025:08:30 09:00:00+00:00", "corrected_time": "2025:08:30 18:00:00+09:00", \
        "source": "mediacreatedate", "stale_fields": ["Keys:CreationDate"]}
        """)
        feed(state, #"{"event": "pipeline_result", "file": "test.mp4", "result": "would_change"}"#)

        XCTAssertEqual(state.diffTableRows[0].originalTimeDisplay, "2025:08:30 09:00:00 UTC")
        XCTAssertEqual(state.diffTableRows[0].correctedTime, "2025:08:30 18:00:00+09:00")
    }

    /// A dry-run preview must not be interrupted by a modal: the conflict is
    /// data the user reads in the table, not a question they answer yet.
    func testDryRunProvidedMismatchDoesNotInterruptThePreview() {
        let state = AppState()
        state.workflowSession.applyMode = false

        feedConflict(state, type: "provided_mismatch")

        XCTAssertFalse(state.workflowSession.showTimezoneConflict)
        XCTAssertEqual(state.workflowSession.timezoneConflictType, "provided_mismatch")
        XCTAssertEqual(state.workflowSession.timezoneConflictProvidedTz, "+0200")
        XCTAssertEqual(state.workflowSession.timezoneConflictFileTimezones?["+0900"], ["test.mp4"])
    }

    /// Applying is where the pipeline refuses without --force-timezone, so that
    /// is where the user is asked to confirm.
    func testApplyProvidedMismatchPromptsForAssent() {
        let state = AppState()
        state.workflowSession.applyMode = true

        feedConflict(state, type: "provided_mismatch")

        XCTAssertTrue(state.workflowSession.showTimezoneConflict)
    }

    /// A batch spanning several zones is refused in both modes, so it always asks.
    func testMixedTimezonesPromptsEvenInDryRun() {
        let state = AppState()
        state.workflowSession.applyMode = false

        feedConflict(state, type: "mixed_timezones")

        XCTAssertTrue(state.workflowSession.showTimezoneConflict)
    }

    /// Confirming the prompt is what unblocks the apply: the re-run the app
    /// launches next must carry --force-timezone, or the pipeline refuses again.
    func testAssentToAProvidedMismatchAddsForceTimezoneToTheNextRun() {
        let state = AppState()
        state.workflowSession.applyMode = true
        feedConflict(state, type: "provided_mismatch")

        state.workflowSession.grantTimezoneAssent()

        XCTAssertFalse(state.workflowSession.showTimezoneConflict)
        let (_, args) = state.workflowSession.buildPipelineArgs()
        XCTAssertTrue(args.contains("--force-timezone"))
        XCTAssertFalse(args.contains("--allow-mixed-timezones"))
    }

    /// A mixed-zone batch needs the other override, so assent must not send the
    /// flag that answers a different question.
    func testAssentToMixedTimezonesAddsAllowMixedToTheNextRun() {
        let state = AppState()
        feedConflict(state, type: "mixed_timezones")

        state.workflowSession.grantTimezoneAssent()

        let (_, args) = state.workflowSession.buildPipelineArgs()
        XCTAssertTrue(args.contains("--allow-mixed-timezones"))
        XCTAssertFalse(args.contains("--force-timezone"))
    }

    /// Assent covers the run it was given for. Starting a fresh run clears it,
    /// so a later batch of untouched files is never relabelled without asking.
    func testStartingAFreshRunDropsEarlierAssent() {
        let state = AppState()
        state.workflowSession.applyMode = true
        feedConflict(state, type: "provided_mismatch")
        state.workflowSession.grantTimezoneAssent()

        state.workflowSession.clearTimezoneAssent()

        let (_, args) = state.workflowSession.buildPipelineArgs()
        XCTAssertFalse(args.contains("--force-timezone"))
        XCTAssertFalse(args.contains("--allow-mixed-timezones"))
        XCTAssertNil(state.workflowSession.timezoneConflictType)
        XCTAssertNil(state.workflowSession.timezoneConflictFileTimezones)
    }
}

/// A timezone is a claim about one batch of footage. These cover the guards that
/// stop a zone declared for one import from silently labelling the next one:
/// pointing the workflow at a different source folder wipes the declaration, and
/// nothing carries a zone from one launch of the app to the next.
final class TimezoneCarryOverTests: XCTestCase {

    private func session() -> WorkflowSession {
        WorkflowSession(profile: MediaProfile(), profileName: "trip")
    }

    /// Picking a new SD card or folder means a new batch, so the zone declared
    /// for the previous one is dropped and the step blocks until it is redeclared.
    func testChangingSourceFolderClearsTheDeclaredTimezone() {
        let session = session()
        session.enabledSteps.insert(.fixTimestamps)
        session.sourceDir.value = "/tmp/import/netherlands"
        session.timezone.value = "Europe/Amsterdam"
        XCTAssertNil(session.validateTimezone())

        session.sourceDir.value = "/tmp/import/korea"

        XCTAssertTrue(session.timezone.current.isEmpty)
        XCTAssertNil(session.timezoneOption)
        XCTAssertNotNil(session.validateTimezone())
        XCTAssertFalse(session.isStepReady(.fixTimestamps))
    }

    /// The zone must survive edits that leave the folder where it was, otherwise
    /// re-picking the same card in the panel would wipe a correct declaration.
    func testRewritingTheSameSourceFolderKeepsTheDeclaredTimezone() {
        let session = session()
        session.sourceDir.value = "/tmp/import/korea"
        session.timezone.value = "Asia/Seoul"

        session.sourceDir.value = "/tmp/import/korea"

        XCTAssertEqual(session.timezone.current, "Asia/Seoul")
        XCTAssertNil(session.validateTimezone())
    }

    /// Declaring a zone and running is the normal path and must still work: the
    /// declaration reaches the pipeline as --timezone for the folder it was made for.
    func testDeclaringAZoneForTheCurrentFolderStillReachesThePipeline() {
        let session = session()
        session.sourceDir.value = "/tmp/import/korea"
        session.timezone.value = "Asia/Seoul"

        let (_, args) = session.buildPipelineArgs()

        guard let index = args.firstIndex(of: "--timezone") else {
            return XCTFail("expected --timezone in \(args)")
        }
        XCTAssertEqual(args[index + 1], "Asia/Seoul")
    }

    /// Nothing persists the declared zone, so a later launch of the app cannot
    /// inherit a zone the user picked for an earlier, unrelated import.
    func testTimezoneIsNotPersistedAcrossAppStateInstances() {
        let first = AppState()
        first.workflowSession.timezone.value = "Europe/Amsterdam"

        let second = AppState()

        XCTAssertTrue(second.workflowSession.timezone.current.isEmpty)
    }
}
