import XCTest
import AppKit
@testable import Jetlag

/// The inspector hosts two AppKit views — the diff table's `NSTableView` and the log's
/// `NSScrollView` — inside SwiftUI. Both are asked for their layout requirements during
/// the window's update-constraints pass. If either reports something derived from its
/// current content, the pass is re-enqueued; with rows and log lines streaming in from a
/// run that happens continuously, and AppKit kills the app once the window has run more
/// update-constraints passes than it has views.
///
/// These tests prove the hosted views stay silent: column widths are written only when
/// they actually change, and the log's scroll view reports no size of its own however
/// much text it holds.
final class InspectorHostedSizingTests: XCTestCase {

    // MARK: - Test doubles

    /// Counts every write to `width`, including writes of a value the column already
    /// has — those are exactly what re-invalidates the table's layout.
    private final class WidthCountingTableColumn: NSTableColumn {
        private(set) var widthAssignments = 0

        override var width: CGFloat {
            get { super.width }
            set {
                widthAssignments += 1
                super.width = newValue
            }
        }

        func resetWidthAssignments() { widthAssignments = 0 }
    }

    /// Counts every priority write, so a test can tell an inert repeat call from one
    /// that touches layout state.
    private final class PriorityCountingScrollView: NSScrollView {
        private(set) var priorityWrites = 0

        override func setContentHuggingPriority(
            _ priority: NSLayoutConstraint.Priority,
            for orientation: NSLayoutConstraint.Orientation
        ) {
            priorityWrites += 1
            super.setContentHuggingPriority(priority, for: orientation)
        }

        override func setContentCompressionResistancePriority(
            _ priority: NSLayoutConstraint.Priority,
            for orientation: NSLayoutConstraint.Orientation
        ) {
            priorityWrites += 1
            super.setContentCompressionResistancePriority(priority, for: orientation)
        }

        func resetPriorityWrites() { priorityWrites = 0 }
    }

    /// Counts every write to `scrollerStyle`, including writes of a value the scroll
    /// view already has — those are exactly what `configureHorizontalScroller`'s
    /// compare-before-assign must avoid on a repeat call.
    private final class ScrollerStyleCountingScrollView: NSScrollView {
        private(set) var scrollerStyleWrites = 0

        override var scrollerStyle: NSScroller.Style {
            get { super.scrollerStyle }
            set {
                scrollerStyleWrites += 1
                super.scrollerStyle = newValue
            }
        }
    }

    private func makeTable(
        minWidths: [CGFloat] = [10, 10]
    ) -> (NSTableView, [WidthCountingTableColumn]) {
        let tableView = NSTableView(frame: NSRect(x: 0, y: 0, width: 600, height: 400))
        let columns = minWidths.enumerated().map { index, minWidth -> WidthCountingTableColumn in
            let column = WidthCountingTableColumn(
                identifier: NSUserInterfaceItemIdentifier("column-\(index)"))
            column.minWidth = minWidth
            tableView.addTableColumn(column)
            return column
        }
        columns.forEach { $0.resetWidthAssignments() }
        return (tableView, columns)
    }

    // MARK: - Column widths

    /// A streaming run recomputes the same column widths for every appended row. Proves
    /// the second pass leaves the columns entirely alone: no width is written, so the
    /// table's layout is not invalidated and the constraint pass is not re-enqueued.
    func testUnchangedColumnWidthsAreNotReassigned() {
        let (tableView, columns) = makeTable()

        TableColumnSizing.applyWidths([200, 140], to: tableView)
        XCTAssertEqual(columns.map(\.width), [200, 140])

        columns.forEach { $0.resetWidthAssignments() }
        let resized = TableColumnSizing.applyWidths([200, 140], to: tableView)

        XCTAssertEqual(resized, [], "no column should have been resized")
        XCTAssertEqual(
            columns.map(\.widthAssignments), [0, 0],
            "re-applying identical widths must not touch the columns")
    }

    /// The guard must not suppress real resizes: when a longer filename widens one
    /// column, that column — and only that column — is written.
    func testChangedColumnWidthIsStillApplied() {
        let (tableView, columns) = makeTable()

        TableColumnSizing.applyWidths([200, 140], to: tableView)
        columns.forEach { $0.resetWidthAssignments() }

        let resized = TableColumnSizing.applyWidths([260, 140], to: tableView)

        XCTAssertEqual(resized, [0])
        XCTAssertEqual(columns.map(\.width), [260, 140])
        XCTAssertEqual(columns.map(\.widthAssignments), [1, 0])
    }

    /// An empty or very short column computes an ideal width below the column's own
    /// minimum, and AppKit clamps the assignment. Comparing against the requested width
    /// would therefore never match and would rewrite the column on every single update —
    /// the streaming case that hangs the constraint pass. Proves the comparison uses the
    /// clamped value the column will actually report.
    func testWidthBelowColumnMinimumIsNotRewrittenEveryPass() {
        let (tableView, columns) = makeTable(minWidths: [90, 10])

        TableColumnSizing.applyWidths([40, 140], to: tableView)
        XCTAssertEqual(columns[0].width, 90, "AppKit clamps the assignment to minWidth")

        columns.forEach { $0.resetWidthAssignments() }
        let resized = TableColumnSizing.applyWidths([40, 140], to: tableView)

        XCTAssertEqual(resized, [])
        XCTAssertEqual(columns.map(\.widthAssignments), [0, 0])
    }

    // MARK: - Hosted scroll views

    /// The log grows by thousands of lines during a run. Proves the hosted scroll view
    /// reports no intrinsic size at all — before and after the text grows — so nothing
    /// about the log's contents can change the min size the inspector column negotiates.
    /// A stock `NSScrollView` happens to answer this way too; the point of pinning it
    /// here is that the log's scroll view now says so explicitly, so a later change that
    /// derives a size from the document view is caught rather than shipped.
    func testLogScrollViewReportsNoIntrinsicSizeAsTextGrows() throws {
        let scrollView = LogTextView.makeScrollView()
        scrollView.frame = NSRect(x: 0, y: 0, width: 400, height: 200)
        let textView = try XCTUnwrap(scrollView.documentView as? NSTextView)

        textView.string = "starting up"
        scrollView.layoutSubtreeIfNeeded()
        let beforeStreaming = scrollView.intrinsicContentSize

        textView.string = (0..<2000)
            .map { "2026-08-26 12:00:00  processing file number \($0) of a Korea import" }
            .joined(separator: "\n")
        scrollView.layoutSubtreeIfNeeded()
        let afterStreaming = scrollView.intrinsicContentSize

        XCTAssertEqual(beforeStreaming, afterStreaming)
        XCTAssertEqual(afterStreaming.width, NSView.noIntrinsicMetric)
        XCTAssertEqual(afterStreaming.height, NSView.noIntrinsicMetric)
    }

    /// A long log line (a path, exiftool output) must never wrap: proves the text view
    /// grows past the scroll view's content width instead of wrapping, a horizontal
    /// scroller is offered, and — matching
    /// `testLogScrollViewReportsNoIntrinsicSizeAsTextGrows` above — the scroll view still
    /// reports no intrinsic size, so the inspector's negotiated width is unaffected.
    func testLogScrollViewNeverWrapsALongLineAndOffersHorizontalScrolling() throws {
        let scrollView = LogTextView.makeScrollView()
        scrollView.frame = NSRect(x: 0, y: 0, width: 480, height: 200)
        let textView = try XCTUnwrap(scrollView.documentView as? NSTextView)

        let textContainer = try XCTUnwrap(textView.textContainer)

        textView.string = "short line"
        textView.layoutManager?.ensureLayout(for: textContainer)
        textView.sizeToFit()
        let shortLineIntrinsicSize = scrollView.intrinsicContentSize
        let shortLineWidth = textView.frame.width

        textView.string = String(repeating: "x", count: 2000)
        textView.layoutManager?.ensureLayout(for: textContainer)
        textView.sizeToFit()
        let longLineIntrinsicSize = scrollView.intrinsicContentSize

        XCTAssertTrue(scrollView.hasHorizontalScroller)
        XCTAssertGreaterThan(
            textView.frame.width, scrollView.contentSize.width,
            "a long line must extend past the panel rather than wrap")
        XCTAssertGreaterThan(textView.frame.width, shortLineWidth)
        XCTAssertEqual(
            shortLineIntrinsicSize, longLineIntrinsicSize,
            "a long line must not change what the scroll view asks of the inspector")
    }

    /// A no-intrinsic-size scroll view still argues for space through its hugging and
    /// compression-resistance priorities. Proves both are below `.defaultLow` on both
    /// axes, so the inspector's configured width — not the log's content — wins.
    func testLogScrollViewYieldsItsSizeToTheInspector() {
        let scrollView = LogTextView.makeScrollView()

        for axis in [NSLayoutConstraint.Orientation.horizontal, .vertical] {
            XCTAssertLessThan(
                scrollView.contentHuggingPriority(for: axis).rawValue,
                NSLayoutConstraint.Priority.defaultLow.rawValue,
                "hugging priority on \(axis) must not pull the inspector's width")
            XCTAssertLessThan(
                scrollView.contentCompressionResistancePriority(for: axis).rawValue,
                NSLayoutConstraint.Priority.defaultLow.rawValue,
                "compression resistance on \(axis) must not push the inspector's width")
        }
    }

    /// The diff table's scroll view gets the same treatment from `updateNSView`, which
    /// runs on every SwiftUI update. Proves the first call lowers both priorities and a
    /// repeat call writes nothing, so calling it from inside the constraint pass cannot
    /// itself invalidate layout.
    func testDetachingATableScrollViewFromItsContentIsInertWhenRepeated() {
        let scrollView = PriorityCountingScrollView(
            frame: NSRect(x: 0, y: 0, width: 600, height: 400))
        scrollView.documentView = NSTableView(frame: scrollView.bounds)

        XCTAssertEqual(
            scrollView.contentCompressionResistancePriority(for: .horizontal),
            .defaultHigh,
            "baseline: AppKit ships a scroll view that resists being squeezed")

        scrollView.detachSizeFromContent()

        XCTAssertGreaterThan(scrollView.priorityWrites, 0)
        for axis in [NSLayoutConstraint.Orientation.horizontal, .vertical] {
            XCTAssertLessThan(
                scrollView.contentHuggingPriority(for: axis).rawValue,
                NSLayoutConstraint.Priority.defaultLow.rawValue)
            XCTAssertLessThan(
                scrollView.contentCompressionResistancePriority(for: axis).rawValue,
                NSLayoutConstraint.Priority.defaultLow.rawValue)
        }

        scrollView.resetPriorityWrites()
        scrollView.detachSizeFromContent()

        XCTAssertEqual(
            scrollView.priorityWrites, 0,
            "already-detached view must not be written to again")
    }

    // MARK: - Always-visible horizontal scrollers

    /// macOS overlay scrollers only appear during a scroll gesture, hiding the fact that
    /// a table or log is wider than the panel. Both hosted scroll views must opt into the
    /// legacy style so a scroller is drawn whenever content overflows.
    func testLogScrollViewUsesLegacyScrollerStyle() {
        let scrollView = LogTextView.makeScrollView()

        XCTAssertEqual(scrollView.scrollerStyle, .legacy)
        XCTAssertTrue(scrollView.hasHorizontalScroller)
        XCTAssertTrue(scrollView.autohidesScrollers)
    }

    /// The Korea dry run (288 rows, #167) computes a `File`/`Timeline`/`Original`/
    /// `Corrected` column width that overflows a narrow panel, leaving `Timestamp`/
    /// `Destination`/`Status` clipped off to the right with no way to discover them.
    /// Proves that once `configureHorizontalScroller` has switched a table's scroll
    /// view to the legacy style, AppKit itself shows a horizontal scroller as soon as
    /// the columns are wider than the scroll view.
    func testHorizontalScrollerIsVisibleWhenColumnsOverflowTheScrollViewWidth() {
        let tableView = NSTableView(frame: NSRect(x: 0, y: 0, width: 1200, height: 400))
        let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("wide"))
        column.width = 1200
        tableView.addTableColumn(column)

        let scrollView = NSScrollView(frame: NSRect(x: 0, y: 0, width: 320, height: 400))
        scrollView.documentView = tableView
        TableColumnSizing.configureHorizontalScroller(for: scrollView)
        scrollView.tile()

        XCTAssertEqual(scrollView.scrollerStyle, .legacy)
        XCTAssertEqual(scrollView.horizontalScroller?.isHidden, false)
    }

    /// The same scroll view with columns narrower than its width never overflows, so
    /// the horizontal scroller stays hidden.
    func testHorizontalScrollerStaysHiddenWhenColumnsFitTheScrollViewWidth() {
        let tableView = NSTableView(frame: NSRect(x: 0, y: 0, width: 200, height: 400))
        let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("narrow"))
        column.width = 100
        tableView.addTableColumn(column)

        let scrollView = NSScrollView(frame: NSRect(x: 0, y: 0, width: 320, height: 400))
        scrollView.documentView = tableView
        TableColumnSizing.configureHorizontalScroller(for: scrollView)
        scrollView.tile()

        XCTAssertEqual(scrollView.scrollerStyle, .legacy)
        XCTAssertEqual(scrollView.horizontalScroller?.isHidden, true)
    }

    /// `configureHorizontalScroller` runs on every `updateNSView` call, same as
    /// `applyWidths`. Proves a repeat call on an already-configured scroll view writes
    /// nothing, so it cannot itself re-invalidate layout (jetlag-m9a).
    func testConfigureHorizontalScrollerIsInertWhenRepeated() {
        let scrollView = ScrollerStyleCountingScrollView(frame: NSRect(x: 0, y: 0, width: 320, height: 400))
        XCTAssertEqual(scrollView.scrollerStyle, .overlay, "baseline: AppKit defaults to overlay scrollers")

        TableColumnSizing.configureHorizontalScroller(for: scrollView)

        XCTAssertEqual(scrollView.scrollerStyle, .legacy)
        XCTAssertTrue(scrollView.hasHorizontalScroller)
        XCTAssertTrue(scrollView.autohidesScrollers)
        XCTAssertEqual(scrollView.scrollerStyleWrites, 1)

        TableColumnSizing.configureHorizontalScroller(for: scrollView)

        XCTAssertEqual(
            scrollView.scrollerStyleWrites, 1,
            "an already-legacy scroll view must not be rewritten")
    }
}
