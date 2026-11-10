import XCTest
import AppKit
@testable import Jetlag

/// `ContentView` is a plain `HStack`, not a `NavigationSplitView` (see its own doc
/// comment for why), so the titlebar has no sidebar column to lay the title out
/// against: AppKit draws `navigationTitle` left-aligned after the traffic lights,
/// where it straddles the sidebar/detail material seam at `ContentView.sidebarWidth`.
/// These tests run against the real window the launched app creates — `JetlagTests`
/// is a hosted unit-test bundle (`TEST_HOST` in project.yml), so `JetlagApp`'s
/// `WindowGroup` has already produced a real `NSWindow` by the time a test runs.
final class WindowTitlebarTests: XCTestCase {
    private func mainWindow() throws -> NSWindow {
        try XCTUnwrap(NSApp.windows.first { $0.contentView != nil && $0.isVisible },
                      "the app's launched window must exist")
    }

    private func firstView<T: NSView>(of type: T.Type, in view: NSView) -> T? {
        if let match = view as? T { return match }
        for subview in view.subviews {
            if let match = firstView(of: type, in: subview) { return match }
        }
        return nil
    }

    /// Tests share the one real window `JetlagApp`'s `WindowGroup` launched with, so a
    /// sidebar selection made by one test is still in effect for the next. Each test
    /// that cares which tab is selected drives the sidebar itself instead of assuming
    /// a starting tab.
    private func selectSidebarRow(_ row: Int, in window: NSWindow) throws {
        let outline = try XCTUnwrap(firstView(of: NSOutlineView.self, in: try XCTUnwrap(window.contentView)),
                                     "the sidebar's outline view must be hosted")
        outline.selectRowIndexes(IndexSet(integer: row), byExtendingSelection: false)
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
    }

    /// AC 1: `.windowToolbarStyle(.unifiedCompact(showsTitle: false))` on the
    /// `WindowGroup` suppresses the titlebar's visible title text.
    func testTitlebarTitleTextIsHidden() throws {
        let window = try mainWindow()
        XCTAssertEqual(window.titleVisibility, .hidden, "the title text must not be drawn in the titlebar")
        XCTAssertEqual(window.toolbarStyle, .unifiedCompact)
    }

    /// AC 2: `navigationTitle` is untouched — it still names the window for Mission
    /// Control, the Window menu and accessibility, even though the text is not drawn.
    /// Switching tabs still changes it, and the title stays hidden either way, proving
    /// AC 1 holds "on either sidebar tab".
    func testNavigationTitleStillNamesTheWindowOnEitherTabWhileStayingHidden() throws {
        let window = try mainWindow()
        try selectSidebarRow(0, in: window)
        XCTAssertEqual(window.title, Strings.Nav.workflow)

        try selectSidebarRow(1, in: window)
        XCTAssertEqual(window.title, Strings.Nav.mediaProfiles, "selecting Profiles must still update the window's name")
        XCTAssertEqual(window.titleVisibility, .hidden, "the title text must stay hidden after switching tabs")

        try selectSidebarRow(0, in: window)
    }

    /// AC 3: the inspector-toggle toolbar button (`.primaryAction` in `WorkflowView`)
    /// still renders on the Workflow tab — hiding the title text must not have removed
    /// the toolbar itself.
    func testToolbarStillRendersItsInspectorToggleButton() throws {
        let window = try mainWindow()
        try selectSidebarRow(0, in: window)
        let toolbar = try XCTUnwrap(window.toolbar, "the toolbar must still be installed")
        XCTAssertEqual(toolbar.items.count, 1, "only the inspector-toggle button is in the toolbar")
    }
}
