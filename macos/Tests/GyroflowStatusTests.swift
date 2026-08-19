import XCTest
@testable import Jetlag

/// Gyroflow is an optional companion app, not something bundled inside Jetlag.
/// download-gyroflow.sh reports whether one is installed and where it came
/// from; the app parses that into the single flag every gyroflow feature is
/// gated on.
final class GyroflowStatusTests: XCTestCase {

    func testParsesAnInstallFoundInApplications() {
        let status = GyroflowStatus.parse("""
        @@present=true
        @@path=/Applications/Gyroflow.app/Contents/MacOS/gyroflow
        @@source=applications
        """)

        XCTAssertTrue(status.isInstalled)
        XCTAssertEqual(status.path, "/Applications/Gyroflow.app/Contents/MacOS/gyroflow")
        XCTAssertEqual(status.source, .applications)
    }

    func testParsesAnInstallJetlagPutInApplicationSupport() {
        let status = GyroflowStatus.parse("""
        @@present=true
        @@path=/Users/x/Library/Application Support/Jetlag/tools/Gyroflow.app/Contents/MacOS/gyroflow
        @@source=jetlag-tools
        """)

        XCTAssertTrue(status.isInstalled)
        XCTAssertEqual(status.source, .jetlagTools)
    }

    func testParsesAbsence() {
        let status = GyroflowStatus.parse("@@present=false")

        XCTAssertFalse(status.isInstalled)
        XCTAssertNil(status.path)
        XCTAssertNil(status.source)
    }

    func testIgnoresProgressChatterAroundThePresenceData() {
        let status = GyroflowStatus.parse("""
        Downloading Gyroflow v1.5.4...
        Installing into /tmp/tools...
        @@present=true
        @@path=/tmp/tools/Gyroflow.app/Contents/MacOS/gyroflow
        @@source=jetlag-tools
        """)

        XCTAssertTrue(status.isInstalled)
        XCTAssertEqual(status.path, "/tmp/tools/Gyroflow.app/Contents/MacOS/gyroflow")
    }

    func testOutputWithNoPresenceDataReadsAsNotInstalled() {
        XCTAssertFalse(GyroflowStatus.parse("curl: (7) Failed to connect").isInstalled)
    }
}

/// The Gyroflow pipeline step must not be offered when no Gyroflow is
/// installed — enabling it would only produce skipped files.
final class GyroflowGatingTests: XCTestCase {

    private func gyroflowProfile() -> MediaProfile {
        var profile = MediaProfile()
        profile.gyroflowEnabled = true
        return profile
    }

    func testGyroflowStepIsOfferedWhenInstalledAndEnabledInProfile() {
        let session = WorkflowSession(
            profile: gyroflowProfile(), profileName: "test", gyroflowAvailable: true
        )

        XCTAssertTrue(session.availableSteps.contains(.gyroflow))
        XCTAssertTrue(session.enabledSteps.contains(.gyroflow))
    }

    func testGyroflowStepIsHiddenWhenNotInstalled() {
        let session = WorkflowSession(
            profile: gyroflowProfile(), profileName: "test", gyroflowAvailable: false
        )

        XCTAssertFalse(session.availableSteps.contains(.gyroflow))
        XCTAssertFalse(session.enabledSteps.contains(.gyroflow))
    }

    func testGyroflowStepIsHiddenWhenInstalledButProfileDoesNotWantIt() {
        let session = WorkflowSession(
            profile: MediaProfile(), profileName: "test", gyroflowAvailable: true
        )

        XCTAssertFalse(session.availableSteps.contains(.gyroflow))
    }

    func testLosingTheInstallDropsAnAlreadyEnabledGyroflowStep() {
        var session = WorkflowSession(
            profile: gyroflowProfile(), profileName: "test", gyroflowAvailable: true
        )
        XCTAssertTrue(session.enabledSteps.contains(.gyroflow))

        session.gyroflowAvailable = false

        XCTAssertFalse(session.availableSteps.contains(.gyroflow))
        XCTAssertFalse(session.enabledSteps.contains(.gyroflow))
    }

    func testAppStatePropagatesInstallStatusToTheActiveSession() {
        let state = AppState()
        state.workflowSession = WorkflowSession(
            profile: gyroflowProfile(), profileName: "test", gyroflowAvailable: false
        )

        state.gyroflowStatus = GyroflowStatus.parse("""
        @@present=true
        @@path=/Applications/Gyroflow.app/Contents/MacOS/gyroflow
        @@source=applications
        """)

        XCTAssertTrue(state.workflowSession.gyroflowAvailable)
        XCTAssertTrue(state.workflowSession.availableSteps.contains(.gyroflow))
    }
}
