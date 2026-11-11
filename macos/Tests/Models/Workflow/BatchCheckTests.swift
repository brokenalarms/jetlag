import XCTest
@testable import Jetlag

/// Covers the one batch-check alert. The pipeline reports every finding of every
/// batch check as a `batch_check` event and says itself whether the run stopped
/// on it; the app asks about the refused ones at once, asks about every finding
/// a preview reported before the apply that follows it, and passes the assent
/// flags the user gave on the next run. Nothing here is per check: the token
/// only picks the alert's text.
final class BatchCheckTests: XCTestCase {

    private func feed(_ state: AppState, _ json: String) {
        state.appendLog(LogLine(text: json, stream: .stdout))
    }

    private func check(_ token: String, flag: String?, refused: Bool,
                       files: [String] = ["a.mp4"]) -> String {
        let list = files.map { "\"\($0)\"" }.joined(separator: ", ")
        let flagField = flag.map { #", "assent_flag": "\#($0)""# } ?? ""
        return #"{"event": "batch_check", "check": "\#(token)", "files": [\#(list)]\#(flagField), "refused": \#(refused)}"#
    }

    /// A refused finding is asked about as soon as the pipeline reports it.
    func testARefusedFindingRaisesTheAlert() {
        let state = AppState()
        state.workflowSession.applyMode = true

        feed(state, check("camera_mismatch", flag: "--allow-camera-mismatch", refused: true))

        XCTAssertEqual(state.workflowSession.pendingChecks.map(\.kind), [.cameraMismatch])
        XCTAssertTrue(state.workflowSession.canGrantPendingChecks)
    }

    /// A finding the run went on past is not a question yet: a preview is never
    /// interrupted by a modal.
    func testAFindingTheRunWentOnPastDoesNotInterrupt() {
        let state = AppState()

        feed(state, check("zone_relabel", flag: "--force-timezone", refused: false))

        XCTAssertTrue(state.workflowSession.pendingChecks.isEmpty)
        XCTAssertEqual(state.workflowSession.reportedChecks.map(\.kind), [.zoneRelabel])
    }

    /// The refused apply has already reset to preview mode when the answer
    /// arrives; granting re-runs that apply with the flag, without asking the
    /// dry-run question it already passed.
    func testGrantingReRunsTheRefusedApplyWithTheFlag() {
        let state = AppState()
        state.workflowSession.applyMode = true
        feed(state, check("protected_sources", flag: "--unlock-protected", refused: true))
        state.workflowSession.noteRunFinished()

        state.workflowSession.grantPendingAssent()

        XCTAssertTrue(state.workflowSession.pendingChecks.isEmpty)
        XCTAssertFalse(state.workflowSession.requestDryRunAssentIfNeeded())
        XCTAssertFalse(state.workflowSession.requestCheckAssentIfNeeded())
        let (_, args) = state.workflowSession.buildPipelineArgs()
        XCTAssertTrue(args.contains("--unlock-protected"))
        XCTAssertTrue(args.contains("--apply"))
    }

    /// A check that refuses a dry run too re-runs the preview, never an apply.
    func testGrantingAfterARefusedDryRunStaysADryRun() {
        let state = AppState()
        feed(state, check("mixed_timezones", flag: "--allow-mixed-timezones", refused: true))
        state.workflowSession.noteRunFinished()

        state.workflowSession.grantPendingAssent()

        let (_, args) = state.workflowSession.buildPipelineArgs()
        XCTAssertTrue(args.contains("--allow-mixed-timezones"))
        XCTAssertFalse(args.contains("--apply"))
    }

    /// Everything a run stopped on is asked about together, and one answer passes
    /// every flag.
    func testSeveralRefusedFindingsAreOneQuestion() {
        let state = AppState()
        state.workflowSession.applyMode = true

        feed(state, check("camera_mismatch", flag: "--allow-camera-mismatch", refused: true))
        feed(state, check("mixed_timezones", flag: "--allow-mixed-timezones", refused: true))
        state.workflowSession.grantPendingAssent()

        let (_, args) = state.workflowSession.buildPipelineArgs()
        XCTAssertTrue(args.contains("--allow-camera-mismatch"))
        XCTAssertTrue(args.contains("--allow-mixed-timezones"))
        XCTAssertEqual(Strings.BatchChecks.title([
            BatchCheck(kind: .cameraMismatch, files: [], groups: [:], chosen: [], assentFlag: nil, refused: true),
            BatchCheck(kind: .mixedTimezones, files: [], groups: [:], chosen: [], assentFlag: nil, refused: true),
        ]), Strings.BatchChecks.severalTitle)
    }

    /// A finding with no assent flag can only be fixed at the source, so there is
    /// nothing to grant.
    func testAFindingWithoutAFlagCannotBeGranted() {
        let state = AppState()

        feed(state, check("filename_unparseable", flag: nil, refused: true, files: ["C0009.MP4"]))

        XCTAssertEqual(state.workflowSession.pendingChecks.map(\.kind), [.filenameUnparseable])
        XCTAssertFalse(state.workflowSession.canGrantPendingChecks)
    }

    /// What a preview found is what its apply would do unasked, so the apply asks
    /// first — destination_occupied, reported after the batch, as much as any.
    func testAnApplyAsksAboutWhatItsPreviewFound() {
        let state = AppState()
        feed(state, check("destination_occupied", flag: "--overwrite", refused: false))
        feed(state, check("filename_unparseable", flag: nil, refused: false))

        XCTAssertFalse(state.workflowSession.requestCheckAssentIfNeeded(), "a dry run never asks")
        state.workflowSession.applyMode = true

        XCTAssertTrue(state.workflowSession.requestCheckAssentIfNeeded())
        XCTAssertEqual(state.workflowSession.pendingChecks.map(\.kind), [.destinationOccupied])

        state.workflowSession.grantPendingAssent()
        XCTAssertFalse(state.workflowSession.requestCheckAssentIfNeeded(),
                       "assent given — the apply must not ask the same question again")
        XCTAssertTrue(state.workflowSession.buildPipelineArgs().args.contains("--overwrite"))
    }

    /// Assent covers the run it was given for. A run the user starts themselves
    /// begins without it, and the findings it answered still stand, so it asks again.
    func testStartingAFreshRunDropsAssentButKeepsTheFindings() {
        let state = AppState()
        state.workflowSession.applyMode = true
        feed(state, check("destination_occupied", flag: "--overwrite", refused: false))
        _ = state.workflowSession.requestCheckAssentIfNeeded()
        state.workflowSession.grantPendingAssent()

        state.workflowSession.clearRunAssent()

        XCTAssertFalse(state.workflowSession.buildPipelineArgs().args.contains("--overwrite"))
        XCTAssertTrue(state.workflowSession.requestCheckAssentIfNeeded())
    }

    /// The findings describe the run that reported them, so they are discarded
    /// with its rows when the next run starts.
    func testFindingsAreDiscardedWithTheRowsTheyExplain() {
        let state = AppState()
        feed(state, check("destination_occupied", flag: "--overwrite", refused: false))

        state.clearLog()

        XCTAssertTrue(state.workflowSession.reportedChecks.isEmpty)
    }

    /// The dry run's completion popup says what the apply will ask about, one
    /// line per finding; an applied run's does not.
    func testTheDryRunSummaryHasALinePerFinding() {
        let camera = BatchCheck(kind: .cameraMismatch, files: ["a.mp4", "b.mp4"], groups: [:], chosen: [],
                                assentFlag: "--allow-camera-mismatch", refused: false)
        let relabel = BatchCheck(kind: .zoneRelabel, files: ["c.mp4"], groups: [:], chosen: [],
                                 assentFlag: "--force-timezone", refused: false)
        func summary(_ mode: PipelineSummary.Mode) -> PipelineSummary {
            PipelineSummary(processed: 3, succeeded: 3, changed: 3, failed: 0, failedFiles: [], mode: mode)
        }

        let dryRun = summary(.dryRun).message(checks: [camera, relabel])
        let applied = summary(.applied).message(checks: [camera, relabel])

        XCTAssertTrue(dryRun.contains(Strings.Workflow.runSummaryCheck(camera)))
        XCTAssertTrue(dryRun.contains(Strings.Workflow.runSummaryCheck(relabel)))
        XCTAssertFalse(applied.contains(Strings.Workflow.runSummaryCheck(camera)))
    }

    /// The message lists the groups the event carries, and the group of files with
    /// no zone evidence is named for the user rather than by its token.
    func testTheMessageListsTheGroups() {
        let mixed = BatchCheck(kind: .mixedTimezones, files: ["a.mp4", "b.mp4", "c.mp4"],
                               groups: ["+0900": ["a.mp4", "b.mp4"], BatchCheck.noZoneGroup: ["c.mp4"]], chosen: [],
                               assentFlag: "--allow-mixed-timezones", refused: true)

        let message = Strings.BatchChecks.message(mixed)

        XCTAssertTrue(message.contains(Strings.BatchChecks.groupLine(label: "+0900", count: 2)))
        XCTAssertTrue(message.contains(Strings.BatchChecks.noZoneGroup))
        XCTAssertFalse(message.contains("\(BatchCheck.noZoneGroup):"))
    }

    /// A relabel says what the files were held against in the same form as
    /// their zones, so a zone name is never compared with an offset.
    func testTheRelabelMessageGivesTheChosenOffset() {
        let relabel = BatchCheck(kind: .zoneRelabel, files: ["a.mp4", "b.mp4"],
                                 groups: ["+0530": ["a.mp4", "b.mp4"]], chosen: ["+0800"],
                                 assentFlag: "--force-timezone", refused: true)

        let message = Strings.BatchChecks.message(relabel)

        XCTAssertTrue(message.contains(Strings.BatchChecks.chosenLine(["+0800"])))
        XCTAssertTrue(message.contains(Strings.BatchChecks.groupLine(label: "+0530", count: 2)))
    }
}
