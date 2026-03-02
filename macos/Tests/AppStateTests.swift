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
