import XCTest
@testable import Jetlag

/// Covers the question Apply asks when the table on screen is not a preview of
/// the run about to happen: nothing was previewed at all, or a setting moved
/// since the preview was made.
///
/// An apply moves and overwrites real files, so the only thing that makes it
/// safe is having read a preview of that exact run. The session compares the
/// arguments it assembled for the last completed dry run against the ones it
/// would send now — no pipeline logic, no inference about what changed.
final class DryRunFreshnessTests: XCTestCase {

    private func makeSession(applyMode: Bool = true) -> WorkflowSession {
        let profile = MediaProfile(
            type: .video,
            sourceDir: "/Volumes/TestCard/DCIM",
            readyDir: "/tmp/ready",
            fileExtensions: [".mp4"]
        )
        let session = WorkflowSession(profile: profile, profileName: "test-profile")
        session.applyMode = applyMode
        return session
    }

    /// Runs a dry run to completion, the only thing that counts as a preview.
    private func completeDryRun(_ session: WorkflowSession) {
        let apply = session.applyMode
        session.applyMode = false
        session.noteRunStarted()
        session.noteRunFinished()
        session.applyMode = apply
    }

    /// Applying with nothing previewed is the case that loses files silently —
    /// the user has no idea where anything is about to go.
    func testApplyWithNoDryRunAsksFirst() {
        let session = makeSession()

        XCTAssertTrue(session.requestDryRunAssentIfNeeded())
        XCTAssertTrue(session.showDryRunStale)
        XCTAssertEqual(session.dryRunStaleReason, .noDryRun)
    }

    /// The preview the user read is the preview that runs, so it goes straight
    /// through — an extra dialog on the normal path trains people to dismiss it.
    func testApplyAfterAnUnchangedDryRunRunsWithoutAsking() {
        let session = makeSession()
        completeDryRun(session)

        XCTAssertFalse(session.requestDryRunAssentIfNeeded())
        XCTAssertFalse(session.showDryRunStale)
    }

    /// The observed bug: a group folder set after the preview means every file
    /// lands somewhere the table never showed.
    func testApplyAfterChangingASettingAsksFirst() {
        let session = makeSession()
        completeDryRun(session)

        session.group = "trip"

        XCTAssertTrue(session.requestDryRunAssentIfNeeded())
        XCTAssertTrue(session.showDryRunStale)
        XCTAssertEqual(session.dryRunStaleReason, .settingsChanged)
    }

    /// A step toggled off changes what the run does just as much as a path does.
    func testTogglingAStepMakesTheDryRunStale() {
        let session = makeSession()
        completeDryRun(session)

        session.enabledSteps.remove(.tag)

        XCTAssertTrue(session.requestDryRunAssentIfNeeded())
        XCTAssertEqual(session.dryRunStaleReason, .settingsChanged)
    }

    /// A cancelled run previewed nothing — it stopped partway through the files,
    /// so it must not stand in for the preview an apply needs.
    func testCancelledDryRunIsNotAPreview() {
        let session = makeSession()
        session.applyMode = false
        session.noteRunStarted()
        session.noteRunCancelled()
        session.applyMode = true

        XCTAssertTrue(session.requestDryRunAssentIfNeeded())
        XCTAssertEqual(session.dryRunStaleReason, .noDryRun)
    }

    /// Assent covers the click it was given for: the next apply of the same
    /// unpreviewed settings has to ask again.
    func testApplyAnywayCoversOneClickOnly() {
        let session = makeSession()
        _ = session.requestDryRunAssentIfNeeded()

        session.grantDryRunStaleAssent()
        XCTAssertFalse(session.showDryRunStale)
        XCTAssertFalse(session.requestDryRunAssentIfNeeded())

        session.clearRunAssent()

        XCTAssertTrue(session.requestDryRunAssentIfNeeded())
        XCTAssertTrue(session.showDryRunStale)
    }

    /// Choosing "Dry run first" leaves the session set up to preview, so the
    /// same click produces the run the user was told to make.
    func testDryRunFirstSwitchesTheRunOutOfApplyMode() {
        let session = makeSession()
        _ = session.requestDryRunAssentIfNeeded()

        session.startDryRunInstead()

        XCTAssertFalse(session.applyMode)
        XCTAssertFalse(session.showDryRunStale)
        XCTAssertFalse(session.requestDryRunAssentIfNeeded())
    }

    /// A preview is never itself interrupted — it destroys nothing.
    func testDryRunNeverAsks() {
        let session = makeSession(applyMode: false)

        XCTAssertFalse(session.requestDryRunAssentIfNeeded())
        XCTAssertFalse(session.showDryRunStale)
    }

    /// The overwrite answer is given for this click, not a setting the user
    /// chose — granting it must not make the preview they just read look stale
    /// and bounce them into a second dialog.
    func testAssentFlagsDoNotMakeAPreviewStale() {
        let session = makeSession()
        completeDryRun(session)

        session.overwriteDestination = true
        session.forceTimezone = true

        XCTAssertFalse(session.requestDryRunAssentIfNeeded())
    }

    /// A dry run made against different settings than the one before it
    /// replaces the record, rather than any earlier match keeping apply quiet.
    func testTheMostRecentDryRunIsTheOneCompared() {
        let session = makeSession()
        completeDryRun(session)

        session.group = "trip"
        completeDryRun(session)

        XCTAssertFalse(session.requestDryRunAssentIfNeeded())

        session.group = ""

        XCTAssertTrue(session.requestDryRunAssentIfNeeded())
        XCTAssertEqual(session.dryRunStaleReason, .settingsChanged)
    }

    /// Cancel is the button the user reaches for mid-run, so the state it
    /// leaves has to be the one an apply then checks.
    func testCancelRunningDiscardsThePreviewInFlight() {
        let state = AppState()
        state.workflowSession.applyMode = false
        state.workflowSession.noteRunStarted()

        state.cancelRunning()
        state.workflowSession.noteRunFinished()
        state.workflowSession.applyMode = true

        XCTAssertTrue(state.workflowSession.requestDryRunAssentIfNeeded())
        XCTAssertEqual(state.workflowSession.dryRunStaleReason, .noDryRun)
    }

    /// An apply run is not a preview: applying again after one still asks.
    func testACompletedApplyIsNotAPreview() {
        let session = makeSession()
        session.noteRunStarted()
        session.noteRunFinished()

        XCTAssertTrue(session.requestDryRunAssentIfNeeded())
        XCTAssertEqual(session.dryRunStaleReason, .noDryRun)
    }
}
