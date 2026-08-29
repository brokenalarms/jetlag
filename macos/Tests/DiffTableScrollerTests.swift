import XCTest
import SwiftUI
import AppKit
@testable import Jetlag

/// The Files table is SwiftUI's `Table`, whose `NSScrollView` SwiftUI configures itself.
/// Whether a horizontal scroller is offered when the columns are wider than the panel can
/// only be proved on that hierarchy — a hand-built `NSTableView` in a bare `NSScrollView`
/// says nothing about it. These tests host the real panel, stream rows into it the way a
/// run does (which is what lets `ColumnAutoSizer` find the table and apply its widths),
/// and read back what AppKit resolved.
final class DiffTableScrollerTests: XCTestCase {

    private func wideRows(_ count: Int) -> [DiffTableRow] {
        (0..<count).map { i in
            var row = DiffTableRow(file: "VID_20250815_17385\(i)_00_0\(i).insv")
            row.originalTime = "2025:08:15 17:38:5\(i)+09:00"
            row.correctedTime = "2025:08:15 17:38:5\(i)+09:00"
            row.timestampAction = "would_fix"
            row.timestampSource = TimestampSource(rawValue: "datetimeoriginal")
            row.dest = "/Volumes/Samsung_990/Videos/Source Video/Insta360/Ready/2025/2025-08-15/VID_20250815_17385\(i)_00_0\(i).insv"
            row.organizeAction = "skipped"
            row.organizeReason = "exists_differs"
            row.pipelineResult = "would_change"
            row.staleFields = ["Keys:CreationDate", "QuickTime:CreateDate"]
            return row
        }
    }

    private func narrowRows(_ count: Int, from first: Int = 0) -> [DiffTableRow] {
        (first..<(first + count)).map { i in
            var row = DiffTableRow(file: "a\(i).mp4")
            row.timestampAction = "no_change"
            row.pipelineResult = "unchanged"
            return row
        }
    }

    private func firstView<T: NSView>(of type: T.Type, in view: NSView) -> T? {
        if let match = view as? T { return match }
        for subview in view.subviews {
            if let match = firstView(of: type, in: subview) { return match }
        }
        return nil
    }

    /// Hosts the workflow detail with the panel open at `width`, then appends rows twice
    /// so the auto-sizer runs with the table in its window, as during a streaming run.
    private func hostPanel(rows: [DiffTableRow], width: CGFloat) throws -> (NSHostingView<WorkflowDetail>, NSTableView, NSScrollView) {
        let state = AppState()
        state.selectedTab = .workflow
        state.showInspector = true
        state.diffTableRows = rows
        let host = NSHostingView(rootView: WorkflowDetail(state: state))
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: width, height: 800),
            styleMask: [.titled, .resizable],
            backing: .buffered,
            defer: false
        )
        window.contentView = host
        host.frame = NSRect(x: 0, y: 0, width: width, height: 800)
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        // Each appended row must be new content: SwiftUI re-runs the auto-sizer only
        // when the computed column widths change, exactly as a live run's rows do.
        for batch in 1...2 {
            state.diffTableRows.append(contentsOf: rows.map { row in
                var longer = DiffTableRow(file: String(repeating: "x", count: batch * 4) + row.file)
                longer.timestampAction = row.timestampAction
                longer.pipelineResult = row.pipelineResult
                return longer
            })
            RunLoop.main.run(until: Date().addingTimeInterval(0.3))
            host.layoutSubtreeIfNeeded()
        }
        let tableView = try XCTUnwrap(firstView(of: NSTableView.self, in: host), "no NSTableView hosted")
        let scrollView = try XCTUnwrap(tableView.enclosingScrollView, "table has no enclosing scroll view")
        return (host, tableView, scrollView)
    }

    /// Columns wider than the panel: the scroll view fills the panel (it scrolls rather
    /// than being clipped by the window) and offers a horizontal scroller in the user's
    /// preferred style.
    func testHorizontalScrollerIsVisibleWhenColumnsExceedThePanel() throws {
        let (host, tableView, scrollView) = try hostPanel(rows: wideRows(12), width: 1400)

        let panelWidth = host.frame.width - WorkflowView.formWidth
        XCTAssertEqual(scrollView.frame.width, panelWidth, accuracy: 2, "the scroll view must fill the panel")
        XCTAssertLessThanOrEqual(scrollView.convert(scrollView.bounds, to: nil).maxX, host.frame.width + 1,
                                 "the scroll view must not extend past the window")
        XCTAssertGreaterThan(tableView.frame.width, scrollView.contentView.bounds.width,
                             "the computed columns should overflow the panel")
        XCTAssertEqual(scrollView.scrollerStyle, NSScroller.preferredScrollerStyle,
                       "the scroller style is the user's system preference, never overridden per view")
        XCTAssertTrue(scrollView.hasHorizontalScroller)
        XCTAssertEqual(scrollView.horizontalScroller?.isHidden, false, "the horizontal scroller must be visible")
    }

    /// Columns that fit: no horizontal scroller is shown.
    func testHorizontalScrollerIsHiddenWhenColumnsFitThePanel() throws {
        let (_, tableView, scrollView) = try hostPanel(rows: narrowRows(4), width: 1900)

        XCTAssertLessThanOrEqual(tableView.frame.width, scrollView.contentView.bounds.width + 1)
        XCTAssertEqual(scrollView.horizontalScroller?.isHidden, true)
    }

    // MARK: - Following the tail

    /// Hosts the panel with `rowCount` rows already listed and nothing else appended,
    /// so the test itself owns every append the table sees.
    private func hostStream(rowCount: Int, width: CGFloat, height: CGFloat) throws
        -> (state: AppState, host: NSHostingView<WorkflowDetail>, tableView: NSTableView, scrollView: NSScrollView) {
        let state = AppState()
        state.selectedTab = .workflow
        state.showInspector = true
        state.diffTableRows = narrowRows(rowCount)
        let host = NSHostingView(rootView: WorkflowDetail(state: state))
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: width, height: height),
            styleMask: [.titled, .resizable],
            backing: .buffered,
            defer: false
        )
        window.contentView = host
        host.frame = NSRect(x: 0, y: 0, width: width, height: height)
        settle(host)
        let tableView = try XCTUnwrap(firstView(of: NSTableView.self, in: host), "no NSTableView hosted")
        let scrollView = try XCTUnwrap(tableView.enclosingScrollView, "table has no enclosing scroll view")
        XCTAssertGreaterThan(tableView.frame.height, scrollView.documentVisibleRect.height,
                             "the rows must overflow the panel or there is nothing to follow")
        return (state, host, tableView, scrollView)
    }

    private func settle(_ host: NSHostingView<WorkflowDetail>) {
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.1))
    }

    private func append(_ count: Int, to state: AppState, host: NSHostingView<WorkflowDetail>) {
        state.diffTableRows.append(contentsOf: narrowRows(count, from: state.diffTableRows.count))
        settle(host)
    }

    private func scrollToBottom(_ scrollView: NSScrollView, _ tableView: NSTableView, host: NSHostingView<WorkflowDetail>) {
        tableView.scrollRowToVisible(tableView.numberOfRows - 1)
        settle(host)
    }

    private func scrollToTop(_ scrollView: NSScrollView, host: NSHostingView<WorkflowDetail>) {
        scrollView.contentView.scroll(to: NSPoint(x: scrollView.documentVisibleRect.minX, y: 0))
        scrollView.reflectScrolledClipView(scrollView.contentView)
        settle(host)
    }

    private func lastRowIsVisible(_ tableView: NSTableView, _ scrollView: NSScrollView) -> Bool {
        guard tableView.numberOfRows > 0 else { return false }
        return scrollView.documentVisibleRect.intersects(tableView.rect(ofRow: tableView.numberOfRows - 1))
    }

    /// A run streaming rows into a table the user is watching from the bottom keeps the
    /// newest row in view, the way the log panel does.
    func testAppendingWithTheLastRowVisibleKeepsItVisible() throws {
        let (state, host, tableView, scrollView) = try hostStream(rowCount: 120, width: 1200, height: 600)
        scrollToBottom(scrollView, tableView, host: host)
        XCTAssertTrue(lastRowIsVisible(tableView, scrollView), "the table should start parked at the tail")

        append(40, to: state, host: host)

        XCTAssertEqual(tableView.numberOfRows, 160, "the appended rows should have reached the table")
        XCTAssertTrue(lastRowIsVisible(tableView, scrollView),
                      "an append made while the tail was visible must keep the tail visible")
    }

    /// Reading a row further up is not interrupted: with the last row scrolled out of
    /// view, rows arriving below leave the scroll position exactly where the user put it.
    func testAppendingWithTheLastRowScrolledOutOfViewLeavesTheScrollPositionAlone() throws {
        let (state, host, tableView, scrollView) = try hostStream(rowCount: 120, width: 1200, height: 600)
        scrollToBottom(scrollView, tableView, host: host)
        scrollToTop(scrollView, host: host)
        XCTAssertFalse(lastRowIsVisible(tableView, scrollView), "the tail should be off screen")
        let parked = scrollView.contentView.bounds.origin

        append(40, to: state, host: host)

        XCTAssertEqual(tableView.numberOfRows, 160, "the appended rows should have reached the table")
        XCTAssertEqual(scrollView.contentView.bounds.origin.y, parked.y, accuracy: 0.5,
                       "rows arriving below the fold must not move the scroll position")
    }

    /// Scrolling back to the bottom re-engages following, so a user who catches up with
    /// the run keeps being carried along by it.
    func testScrollingBackToTheBottomResumesFollowing() throws {
        let (state, host, tableView, scrollView) = try hostStream(rowCount: 120, width: 1200, height: 600)
        scrollToBottom(scrollView, tableView, host: host)
        scrollToTop(scrollView, host: host)
        append(40, to: state, host: host)

        scrollToBottom(scrollView, tableView, host: host)
        append(40, to: state, host: host)

        XCTAssertEqual(tableView.numberOfRows, 200, "the appended rows should have reached the table")
        XCTAssertTrue(lastRowIsVisible(tableView, scrollView),
                      "returning to the bottom must resume following the tail")
    }
}
