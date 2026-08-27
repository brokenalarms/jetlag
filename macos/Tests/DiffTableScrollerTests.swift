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

    private func narrowRows(_ count: Int) -> [DiffTableRow] {
        (0..<count).map { i in
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
    /// than being clipped by the window), and a legacy horizontal scroller is visible
    /// without any gesture.
    func testHorizontalScrollerIsVisibleWhenColumnsExceedThePanel() throws {
        let (host, tableView, scrollView) = try hostPanel(rows: wideRows(12), width: 1400)

        let panelWidth = host.frame.width - WorkflowView.formWidth
        XCTAssertEqual(scrollView.frame.width, panelWidth, accuracy: 2, "the scroll view must fill the panel")
        XCTAssertLessThanOrEqual(scrollView.convert(scrollView.bounds, to: nil).maxX, host.frame.width + 1,
                                 "the scroll view must not extend past the window")
        XCTAssertGreaterThan(tableView.frame.width, scrollView.contentView.bounds.width,
                             "the computed columns should overflow the panel")
        XCTAssertEqual(scrollView.scrollerStyle, .legacy)
        XCTAssertTrue(scrollView.horizontalScroller is AlwaysVisibleScroller,
                      "the scroller class is what keeps the style legacy across AppKit re-syncs")
        XCTAssertTrue(scrollView.hasHorizontalScroller)
        XCTAssertEqual(scrollView.horizontalScroller?.isHidden, false, "the horizontal scroller must be visible")
    }

    /// Columns that fit: no horizontal scroller is shown.
    func testHorizontalScrollerIsHiddenWhenColumnsFitThePanel() throws {
        let (_, tableView, scrollView) = try hostPanel(rows: narrowRows(4), width: 1900)

        XCTAssertLessThanOrEqual(tableView.frame.width, scrollView.contentView.bounds.width + 1)
        XCTAssertEqual(scrollView.horizontalScroller?.isHidden, true)
    }
}
