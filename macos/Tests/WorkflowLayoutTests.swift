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

    /// Every point the window has beyond the form goes to the panel, up to the panel's
    /// cap (twice the width of everything beside it).
    func testPanelTakesTheRemainderUpToItsCap() {
        for width: CGFloat in [1200, 1900, 3000] {
            guard let panel = panelWidth(at: width) else {
                XCTFail("the panel's log view was not hosted at \(width)pt")
                continue
            }
            let expected = min(width - WorkflowView.formWidth, WorkflowDetail.panelMaxWidth)
            XCTAssertEqual(panel, expected, accuracy: 2, "panel at \(width)pt")
        }
    }

    /// The whole window content — sidebar, form, panel — has a derived size range and no
    /// declared window width: closed, it resolves to sidebar + form however much it is
    /// offered, which is what lets `windowResizability(.contentSize)` shrink-wrap the
    /// window; open, its minimum rises by the panel's minimum.
    func testWindowContentSizesToItsChildren() {
        func resolvedWidth(panelOpen: Bool, offered: CGFloat) -> CGFloat {
            let controller = NSHostingController(rootView: ContentView(state: workflowState(panelOpen: panelOpen)))
            return controller.sizeThatFits(in: NSSize(width: offered, height: 900)).width
        }
        let closedNarrow = resolvedWidth(panelOpen: false, offered: 0)
        let closedWide = resolvedWidth(panelOpen: false, offered: 1900)
        XCTAssertEqual(closedNarrow, closedWide, accuracy: 1, "closed, the content has one width")
        XCTAssertEqual(closedWide, ContentView.sidebarWidth + WorkflowView.formWidth, accuracy: 2)

        let openMinimum = resolvedWidth(panelOpen: true, offered: 0)
        XCTAssertEqual(openMinimum - closedNarrow, InspectorPanel.minWidth, accuracy: 2)
        // Open, the panel takes what it is offered up to its cap: never wider than
        // everything beside it, so the window at most doubles.
        let cap = ContentView.sidebarWidth + WorkflowView.formWidth + WorkflowDetail.panelMaxWidth
        XCTAssertEqual(resolvedWidth(panelOpen: true, offered: 1900), 1900, accuracy: 2, "open, the content fills what it is offered between its minimum and the cap")
        XCTAssertEqual(resolvedWidth(panelOpen: true, offered: 4000), cap, accuracy: 2, "open, the content stops at the cap")
    }

    /// Columns are pinned to the top: a short form (no profile chosen yet) sits at the
    /// top of the window, not floating in the middle of it.
    func testFormIsPinnedToTheTopOfTheWindow() {
        let state = AppState()
        state.selectedTab = .workflow
        state.showInspector = false
        let host = NSHostingView(rootView: ContentView(state: state))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1400, height: 900),
                              styleMask: [.titled, .resizable], backing: .buffered, defer: false)
        window.contentView = host
        host.frame = NSRect(x: 0, y: 0, width: 1400, height: 900)
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))

        guard let picker = firstView(of: NSPopUpButton.self, in: host) else {
            return XCTFail("the profile picker was not hosted")
        }
        let top = picker.convert(picker.bounds, to: nil).maxY
        XCTAssertGreaterThan(top, 900 - 120, "the profile picker must sit within the top of the window, not mid-height")
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

    /// The form's height is its content's, like its width: enabling a step that adds
    /// controls raises the content's minimum height, which is what lets the window grow
    /// to fit instead of the form scrolling inside it. No scroll view may wrap the form.
    func testEnablingAStepRaisesTheContentMinimumHeight() {
        let state = AppState()
        state.selectedTab = .workflow
        state.showInspector = false
        state.workflowSession = WorkflowSession(profileName: "probe", gyroflowAvailable: false)
        state.workflowSession.enabledSteps.remove(.archiveSource)

        // The form alone: the sidebar beside it is a List, which is a scroll view and
        // height-flexible by design, so it must not take part in this measurement.
        func minimumHeight() -> CGFloat {
            NSHostingController(rootView: WorkflowView(state: state))
                .sizeThatFits(in: NSSize(width: WorkflowView.formWidth, height: 0)).height
        }
        let without = minimumHeight()
        state.workflowSession.enabledSteps.insert(.archiveSource)
        let with = minimumHeight()

        XCTAssertGreaterThan(without, 0, "the form must declare a height of its own")
        XCTAssertGreaterThan(with, without, "enabling Archive Source must make the form, and so the window, taller")

        let host = NSHostingView(rootView: WorkflowView(state: state))
        host.frame = NSRect(x: 0, y: 0, width: WorkflowView.formWidth, height: with)
        host.layoutSubtreeIfNeeded()
        XCTAssertNil(firstScrollView(in: host), "the form must not scroll; its height sizes the window")
    }

    private func firstScrollView(in view: NSView) -> NSScrollView? {
        if let scroll = view as? NSScrollView { return scroll }
        for subview in view.subviews {
            if let scroll = firstScrollView(in: subview) { return scroll }
        }
        return nil
    }
}
