import XCTest
import SwiftUI
import AppKit
@testable import Jetlag

/// A run captures its arguments at launch: mid-run edits to the profile, a step
/// field, or the Dry Run/Apply mode only desync the form from the run already
/// producing output. These tests confirm the form's AppKit-backed controls (the
/// profile picker, step text fields and checkboxes, and the Dry Run/Apply picker)
/// go inert while `state.isRunning` is true and re-enable once it isn't — the
/// exact "Group field accepted typing" regression the bug reported.
final class WorkflowRunningStateTests: XCTestCase {

    private func host<V: View>(_ view: V, height: CGFloat = 1600) -> NSHostingView<V> {
        let host = NSHostingView(rootView: view)
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: WorkflowView.formWidth, height: height),
            styleMask: [.titled, .resizable],
            backing: .buffered,
            defer: false
        )
        window.contentView = host
        host.frame = NSRect(x: 0, y: 0, width: WorkflowView.formWidth, height: height)
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        host.layoutSubtreeIfNeeded()
        return host
    }

    private func allControls(in view: NSView) -> [NSControl] {
        var found: [NSControl] = []
        if let control = view as? NSControl {
            found.append(control)
        }
        for subview in view.subviews {
            found.append(contentsOf: allControls(in: subview))
        }
        return found
    }

    private func makeState() -> AppState {
        let state = AppState()
        state.selectedTab = .workflow
        state.workflowSession = WorkflowSession(profileName: "probe", gyroflowAvailable: false)
        return state
    }

    private func groupField(in controls: [NSControl]) -> NSTextField? {
        controls.compactMap { $0 as? NSTextField }.first { $0.placeholderString == Strings.Workflow.groupPlaceholder }
    }

    /// While idle, the profile picker, the step text fields (including Group — the
    /// field the bug reported accepting typing mid-run), and the Dry Run/Apply
    /// picker are all present and enabled. Once a run starts every one of them
    /// goes inert.
    func testFormControlsDisableWhileRunning() {
        let state = makeState()

        let idleControls = allControls(in: host(WorkflowView(state: state)))
        XCTAssertTrue(idleControls.contains { $0 is NSPopUpButton }, "expected the profile picker to be hosted")
        XCTAssertTrue(idleControls.contains { $0 is NSSegmentedControl }, "expected the Dry Run/Apply picker to be hosted")
        guard let idleGroupField = groupField(in: idleControls) else {
            return XCTFail("expected the Group field to be hosted")
        }
        XCTAssertTrue(idleGroupField.isEnabled, "the Group field must accept typing before a run starts")

        state.isRunning = true
        let runningControls = allControls(in: host(WorkflowView(state: state)))
        guard let runningGroupField = groupField(in: runningControls) else {
            return XCTFail("expected the Group field to still be hosted while running")
        }
        XCTAssertFalse(runningGroupField.isEnabled, "the Group field must not accept typing while a run is in progress")

        for control in runningControls {
            XCTAssertFalse(control.isEnabled, "\(control) must be disabled while a run is in progress")
        }
    }

    /// Once a run finishes (`isRunning` goes back to `false`), the form returns to
    /// exactly the set of enabled controls it had before the run — nothing is left
    /// stuck disabled.
    func testFormControlsReenableAfterRunFinishes() {
        let state = makeState()
        let idleEnabledCount = allControls(in: host(WorkflowView(state: state))).filter(\.isEnabled).count

        state.isRunning = true
        _ = host(WorkflowView(state: state))

        state.isRunning = false
        let reidleEnabledCount = allControls(in: host(WorkflowView(state: state))).filter(\.isEnabled).count

        XCTAssertEqual(reidleEnabledCount, idleEnabledCount, "expected every control to re-enable once the run finishes")
    }
}
