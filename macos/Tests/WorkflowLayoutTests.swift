import XCTest
import SwiftUI
import AppKit
@testable import Jetlag

/// The workflow form sits beside its files/log panel. The form is a fixed-width column of
/// controls; the panel is the only thing that flexes. These tests measure what AppKit
/// actually resolves — the frames of the hosted views and the content's minimum size —
/// rather than any number the views declare.
final class WorkflowLayoutTests: XCTestCase {

    private func host<V: View>(_ view: V, width: CGFloat) -> NSHostingView<V> {
        let host = NSHostingView(rootView: view)
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: width, height: 900),
            styleMask: [.titled, .resizable],
            backing: .buffered,
            defer: false
        )
        window.contentView = host
        host.frame = NSRect(x: 0, y: 0, width: width, height: 900)
        host.layoutSubtreeIfNeeded()
        return host
    }

    private func firstView<T: NSView>(of type: T.Type, in view: NSView) -> T? {
        if let match = view as? T { return match }
        for subview in view.subviews {
            if let match = firstView(of: type, in: subview) { return match }
        }
        return nil
    }

    private func workflowState(panelOpen: Bool) -> AppState {
        let state = AppState()
        state.selectedTab = .workflow
        state.showInspector = panelOpen
        state.showLogOutput = panelOpen
        return state
    }

    /// The panel's width as AppKit laid it out: the log's scroll view fills the panel.
    private func panelWidth(at width: CGFloat) -> CGFloat? {
        let hosted = host(WorkflowDetail(state: workflowState(panelOpen: true)), width: width)
        return firstView(of: ContentAgnosticScrollView.self, in: hosted)?.frame.width
    }

    /// The form never grows to fill the space it is offered: alone in a wide window it
    /// still resolves to its own width, so widening the window can only ever widen the
    /// panel.
    func testFormKeepsItsWidthHoweverMuchSpaceItIsOffered() {
        for width: CGFloat in [WorkflowView.formWidth, 1400, 1900] {
            let controller = NSHostingController(rootView: WorkflowDetail(state: workflowState(panelOpen: false)))
            let resolved = controller.sizeThatFits(in: NSSize(width: width, height: 900)).width
            XCTAssertEqual(resolved, WorkflowView.formWidth, accuracy: 1, "offered \(width)pt")
        }
    }

    /// Every point the window has beyond the form goes to the panel.
    func testPanelTakesTheRemainder() {
        for width: CGFloat in [1400, 1900] {
            guard let panel = panelWidth(at: width) else {
                XCTFail("the panel's log view was not hosted at \(width)pt")
                continue
            }
            XCTAssertEqual(panel, width - WorkflowView.formWidth, accuracy: 2, "panel at \(width)pt")
        }
    }

    /// Opening the panel raises the content's minimum by the panel's own minimum — that
    /// growth is what `windowResizability(.contentMinSize)` turns into a wider window,
    /// rather than a narrower form.
    func testOpeningThePanelRaisesTheContentMinimum() {
        func minimumWidth(panelOpen: Bool) -> CGFloat {
            let controller = NSHostingController(rootView: WorkflowDetail(state: workflowState(panelOpen: panelOpen)))
            return controller.sizeThatFits(in: NSSize(width: 0, height: 900)).width
        }
        let closed = minimumWidth(panelOpen: false)
        let open = minimumWidth(panelOpen: true)

        XCTAssertEqual(closed, WorkflowView.formWidth, accuracy: 1)
        XCTAssertEqual(open - closed, InspectorPanel.minWidth, accuracy: 2)
    }
}
