import XCTest
import SwiftUI
import AppKit
@testable import Jetlag

/// The split view has to settle three columns — sidebar, workflow form, inspector — for
/// whatever width the window happens to be. It can only do that if each column has one
/// legal answer. When the form's column could be squeezed below the form's own width,
/// opening the inspector against the right edge of the screen left AppKit no solution: it
/// pushed the sidebar and form off the left edge, and re-ran the negotiation on every
/// resize until the window's update-constraints pass was aborted.
///
/// These tests pin the two halves of that: the form measures the same width no matter how
/// much or how little space it is offered, and the window's declared minimum is wide
/// enough to hold every visible column so AppKit grows the window rather than overlapping.
final class SplitViewLayoutTests: XCTestCase {

    // MARK: - Test doubles

    /// Records the width SwiftUI actually resolves for the view it is attached to.
    private final class WidthProbe: NSView {
        var onLayout: ((CGFloat) -> Void)?

        override func layout() {
            super.layout()
            onLayout?(bounds.width)
        }
    }

    private struct WidthProbeView: NSViewRepresentable {
        let record: (CGFloat) -> Void

        func makeNSView(context: Context) -> WidthProbe {
            let probe = WidthProbe()
            probe.onLayout = record
            return probe
        }

        func updateNSView(_ probe: WidthProbe, context: Context) {
            probe.onLayout = record
        }
    }

    /// Lays out `view` at each of `widths` in an offscreen window and returns every width
    /// the probe attached behind it resolved to.
    private func resolvedWidths<V: View>(
        of view: (@escaping (CGFloat) -> Void) -> V,
        offered widths: [CGFloat]
    ) -> [CGFloat] {
        var observed: [CGFloat] = []
        let host = NSHostingView(rootView: view { observed.append($0) })
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: widths[0], height: 900),
            styleMask: [.titled, .resizable],
            backing: .buffered,
            defer: false
        )
        window.contentView = host

        for width in widths {
            window.setContentSize(NSSize(width: width, height: 900))
            host.frame = NSRect(x: 0, y: 0, width: width, height: 900)
            host.layoutSubtreeIfNeeded()
        }
        return observed
    }

    // MARK: - The form's width is invariant

    /// The workflow form is a column of fixed-size controls. Proves it resolves to exactly
    /// one width whether the split view offers it less space than it needs (the squeeze
    /// that clipped "…est" and "…y companion files" off the left edge) or far more (a
    /// 1931pt window with the inspector closed) — so widening or narrowing the window can
    /// never change what the form asks the split view for.
    func testFormKeepsOneWidthHoweverMuchSpaceItIsOffered() {
        let offered: [CGFloat] = [
            400,
            SplitViewLayout.detailMinWidth,
            1200,
            1900,
        ]

        let widths = resolvedWidths(
            of: { record in
                WorkflowView(state: AppState())
                    .background(WidthProbeView(record: record))
            },
            offered: offered
        )

        XCTAssertFalse(widths.isEmpty, "the probe never laid out — the form was not hosted")
        XCTAssertEqual(
            Set(widths), [SplitViewLayout.formContentWidth],
            "the form must measure \(SplitViewLayout.formContentWidth)pt at every offered width, got \(Set(widths).sorted())"
        )
    }

    // MARK: - The window's declared minimum

    /// Proves the window's minimum width leaves room for every visible column, so AppKit
    /// satisfies it by growing the window rather than by overlapping the sidebar and form.
    func testWindowMinimumFitsEveryVisibleColumn() {
        XCTAssertGreaterThanOrEqual(
            SplitViewLayout.windowMinWidth(inspectorVisible: false),
            SplitViewLayout.sidebarMinWidth + SplitViewLayout.formContentWidth,
            "with the inspector closed the window must still hold the sidebar and the form"
        )
        XCTAssertGreaterThanOrEqual(
            SplitViewLayout.windowMinWidth(inspectorVisible: true),
            SplitViewLayout.sidebarMinWidth + SplitViewLayout.formContentWidth + SplitViewLayout.inspectorMinWidth,
            "with the inspector open the window must hold the sidebar, the form and the inspector"
        )
    }

    /// Opening the inspector must make the window wider, not steal the form's space.
    /// Proves the declared minimum grows by the inspector's own minimum, which is what
    /// `windowResizability(.contentMinSize)` acts on to push the window's right edge out.
    func testOpeningTheInspectorRaisesTheWindowMinimumByTheInspectorsWidth() {
        let closed = SplitViewLayout.windowMinWidth(inspectorVisible: false)
        let open = SplitViewLayout.windowMinWidth(inspectorVisible: true)

        XCTAssertEqual(open - closed, SplitViewLayout.inspectorMinWidth)
    }

    /// The arithmetic above is only worth anything if the number reaches AppKit. Proves
    /// the hosted `ContentView` reports a fitting width that holds every visible column, and
    /// that the number it reports grows when the inspector is open — that growth is what
    /// `windowResizability(.contentMinSize)` turns into a wider window.
    func testHostedContentReportsAMinimumThatHoldsEveryVisibleColumn() {
        func fittingWidth(inspectorVisible: Bool) -> CGFloat {
            let state = AppState()
            state.selectedTab = .workflow
            state.showInspector = inspectorVisible
            let host = NSHostingView(rootView: ContentView(state: state))
            let window = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 1931, height: 900),
                styleMask: [.titled, .resizable],
                backing: .buffered,
                defer: false
            )
            window.contentView = host
            host.layoutSubtreeIfNeeded()
            return host.fittingSize.width
        }

        let closed = fittingWidth(inspectorVisible: false)
        let open = fittingWidth(inspectorVisible: true)

        XCTAssertGreaterThanOrEqual(closed, SplitViewLayout.windowMinWidth(inspectorVisible: false))
        XCTAssertGreaterThanOrEqual(open, SplitViewLayout.windowMinWidth(inspectorVisible: true))
        XCTAssertGreaterThan(
            open, closed,
            "opening the inspector must raise the window's minimum, not squeeze the form"
        )
    }

    /// The detail column must never be the thing that gives way: proves its declared
    /// minimum holds the whole form, so the split view cannot resolve it to a width the
    /// form does not fit in.
    func testDetailColumnMinimumHoldsTheWholeForm() {
        XCTAssertGreaterThanOrEqual(
            SplitViewLayout.detailMinWidth,
            SplitViewLayout.formContentWidth
        )
    }

    /// The window minimum is what the split view is handed, so it must be at least the sum
    /// of what the columns declare to the split view — otherwise there is no assignment of
    /// column widths that satisfies every constraint and AppKit renegotiates forever.
    func testColumnMinimumsAddUpToTheWindowMinimum() {
        XCTAssertEqual(
            SplitViewLayout.windowMinWidth(inspectorVisible: true),
            SplitViewLayout.sidebarMinWidth
                + SplitViewLayout.detailMinWidth
                + SplitViewLayout.inspectorMinWidth
        )
    }
}
