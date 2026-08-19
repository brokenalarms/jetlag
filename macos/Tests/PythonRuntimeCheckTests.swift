import XCTest
@testable import Jetlag

/// On a Mac with neither Xcode nor the Command Line Tools installed,
/// /usr/bin/python3 is a shim that opens the developer-tools install dialog
/// instead of running. These tests prove the app works out whether the pipeline
/// can start *without* invoking that shim, and refuses the run with a message
/// naming what to install rather than failing opaquely.
final class PythonRuntimeCheckTests: XCTestCase {

    private func check(
        developerDirectory: Bool,
        override: String? = nil,
        onPath: String? = nil,
        onDeveloperDirectoryProbe: @escaping () -> Void = {}
    ) -> PythonRuntimeCheck {
        PythonRuntimeCheck(
            developerDirectoryPresent: {
                onDeveloperDirectoryProbe()
                return developerDirectory
            },
            overrideInterpreter: { override },
            pathInterpreter: { onPath }
        )
    }

    // A clean install: no developer directory, no other interpreter anywhere.
    // The only python3 on the machine is the stub, so the run must be refused.
    func testNoDeveloperDirectoryAndNoOtherInterpreterIsUnusable() {
        let runtime = check(developerDirectory: false)

        XCTAssertEqual(runtime.status, .commandLineToolsMissing)
    }

    // Any machine with Xcode or the Command Line Tools: /usr/bin/python3 is a
    // real interpreter and nothing about the run changes.
    func testDeveloperDirectoryPresentIsReady() {
        let runtime = check(developerDirectory: true)

        XCTAssertEqual(runtime.status, .ready)
    }

    // JETLAG_PYTHON is what ensure-venv.sh resolves first, so a pinned
    // interpreter makes the stub irrelevant even with no developer directory.
    func testPinnedInterpreterIsUsedWithoutADeveloperDirectory() {
        let runtime = check(developerDirectory: false, override: "/opt/homebrew/bin/python3")

        XCTAssertEqual(runtime.status, .ready)
    }

    // ensure-venv.sh falls back to a python3 elsewhere on PATH, so a Homebrew
    // install is enough to run even with no developer directory.
    func testInterpreterOnPathIsUsedWithoutADeveloperDirectory() {
        let runtime = check(developerDirectory: false, onPath: "/opt/homebrew/bin/python3")

        XCTAssertEqual(runtime.status, .ready)
    }

    // A pinned interpreter short-circuits the check: the developer directory is
    // never probed when the user already told the scripts what to run.
    func testPinnedInterpreterSkipsTheDeveloperDirectoryProbe() {
        var probes = 0
        let runtime = check(
            developerDirectory: false,
            override: "/opt/homebrew/bin/python3",
            onDeveloperDirectoryProbe: { probes += 1 }
        )

        XCTAssertEqual(runtime.status, .ready)
        XCTAssertEqual(probes, 0)
    }

    // The stub verdict is reached from the developer-directory probe alone —
    // nothing in the check executes an interpreter, which is what would raise
    // the install dialog.
    func testStubVerdictComesFromTheDeveloperDirectoryProbe() {
        var probes = 0
        let runtime = check(developerDirectory: false, onDeveloperDirectoryProbe: { probes += 1 })

        XCTAssertEqual(runtime.status, .commandLineToolsMissing)
        XCTAssertEqual(probes, 1)
    }

    // The refusal a user sees has to name the thing to install and the exact
    // command that installs it, or it is no better than the opaque failure.
    func testBlockedRunSurfacesAnAlertNamingTheInstallCommand() {
        let state = AppState()

        XCTAssertFalse(state.canRunPipeline(check: check(developerDirectory: false)))
        guard let alert = state.pythonRuntimeAlert else {
            return XCTFail("a blocked run must raise an alert")
        }
        XCTAssertTrue(alert.contains("Command Line Tools"), "alert: \(alert)")
        XCTAssertTrue(alert.contains("xcode-select --install"), "alert: \(alert)")
    }

    // The working path is untouched: the run proceeds and no alert is raised.
    func testWorkingInterpreterRunsWithoutAnAlert() {
        let state = AppState()

        XCTAssertTrue(state.canRunPipeline(check: check(developerDirectory: true)))
        XCTAssertNil(state.pythonRuntimeAlert)
    }

    // Installing the tools and retrying clears the refusal rather than leaving
    // a stale alert bound to the sheet.
    func testAStaleAlertClearsOnceTheInterpreterWorks() {
        let state = AppState()
        _ = state.canRunPipeline(check: check(developerDirectory: false))

        XCTAssertTrue(state.canRunPipeline(check: check(developerDirectory: true)))
        XCTAssertNil(state.pythonRuntimeAlert)
    }
}
