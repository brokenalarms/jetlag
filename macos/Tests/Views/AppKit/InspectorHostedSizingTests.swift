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

        func forgetWrites() {
            scrollerStyleWrites = 0
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
        let scrollView = LogScrollView.make()
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

    /// The log is a terminal transcript: a long log line (a path, exiftool output) must
    /// wrap to the panel width like a terminal wraps as you resize, never overflow with a
    /// horizontal scroller. Proves the text view's frame stays pinned to the scroll view's
    /// content width and the line lays out across more than one visual line.
    func testLogScrollViewWrapsALongLine() throws {
        let scrollView = LogScrollView.make()
        scrollView.frame = NSRect(x: 0, y: 0, width: 480, height: 200)
        let textView = try XCTUnwrap(scrollView.documentView as? NSTextView)
        let textContainer = try XCTUnwrap(textView.textContainer)
        let layoutManager = try XCTUnwrap(textView.layoutManager)

        textView.string = String(repeating: "x", count: 2000)
        scrollView.layoutSubtreeIfNeeded()
        layoutManager.ensureLayout(for: textContainer)

        XCTAssertFalse(scrollView.hasHorizontalScroller)
        XCTAssertEqual(
            textView.frame.width, scrollView.contentSize.width,
            "the text view's frame must track the scroll view's content width, not the text")

        let glyphRange = layoutManager.glyphRange(for: textContainer)
        var visualLineCount = 0
        var glyphIndex = glyphRange.location
        while glyphIndex < NSMaxRange(glyphRange) {
            var lineRange = NSRange()
            layoutManager.lineFragmentRect(forGlyphAt: glyphIndex, effectiveRange: &lineRange)
            visualLineCount += 1
            glyphIndex = NSMaxRange(lineRange)
        }
        XCTAssertGreaterThan(
            visualLineCount, 1,
            "a 2000-character line must wrap across more than one visual line")
    }

    /// The scripts write ANSI SGR colour codes for terminal-coloured stderr (e.g.
    /// `\u{1B}[36m…\u{1B}[0m`). Proves the log's displayed text never carries them, even
    /// though the underlying `LogLine.text` still holds the raw bytes.
    func testDisplayTextStripsANSIEscapeSequences() {
        let line = LogLine(
            text: "\u{1B}[36m🔍 VID_20250815_173854_00_014.insv\u{1B}[0m",
            stream: .stderr)

        let displayText = LogTextView.displayText(for: [line])

        XCTAssertEqual(displayText, "🔍 VID_20250815_173854_00_014.insv")
        XCTAssertFalse(displayText.contains("\u{1B}"))
    }

    /// A no-intrinsic-size scroll view still argues for space through its hugging and
    /// compression-resistance priorities. Proves both are below `.defaultLow` on both
    /// axes, so the inspector's configured width — not the log's content — wins.
    func testLogScrollViewYieldsItsSizeToTheInspector() {
        let scrollView = LogScrollView.make()

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

    // MARK: - Horizontal scroller configuration

    /// The scroller style is the user's system preference. Proves the table's
    /// configuration never writes `scrollerStyle` — overriding "Show scroll bars" for
    /// one view is not the app's call — and that a repeat call on an already-configured
    /// scroll view writes nothing at all, so it cannot re-invalidate layout from the
    /// per-row updates it runs on (jetlag-m9a).
    func testConfigureHorizontalScrollerRespectsThePreferredStyleAndIsInertWhenRepeated() {
        let scrollView = ScrollerStyleCountingScrollView(frame: NSRect(x: 0, y: 0, width: 320, height: 400))
        let baseline = scrollView.scrollerStyle

        TableColumnSizing.configureHorizontalScroller(for: scrollView)

        XCTAssertEqual(scrollView.scrollerStyle, baseline, "the style must be left to the system preference")
        XCTAssertEqual(scrollView.scrollerStyleWrites, 0)
        XCTAssertTrue(scrollView.hasHorizontalScroller)
        XCTAssertTrue(scrollView.autohidesScrollers)

        TableColumnSizing.configureHorizontalScroller(for: scrollView)

        XCTAssertEqual(scrollView.scrollerStyleWrites, 0)
    }

    /// Counts `flashScrollers()` calls, which are the only observable side effect of
    /// revealing an overflow.
    private final class FlashCountingScrollView: NSScrollView {
        private(set) var flashes = 0
        override func flashScrollers() { flashes += 1 }
    }

    /// Overlay scrollers hide until a gesture, so growing past the panel needs the
    /// system's own cue. Proves the flash fires only when a column width actually
    /// changed and the document now overflows — never on an idle update, and never
    /// when the table fits.
    func testOverflowIsRevealedOnlyWhenAResizeMakesTheTableOverflow() {
        let scrollView = FlashCountingScrollView(frame: NSRect(x: 0, y: 0, width: 320, height: 400))
        // A table sizes itself to its columns once tiled, so the overflow comes from
        // a column, as it does in the app.
        let tableView = NSTableView(frame: NSRect(x: 0, y: 0, width: 1200, height: 400))
        let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("wide"))
        column.width = 1200
        tableView.addTableColumn(column)
        scrollView.documentView = tableView
        scrollView.tile()

        TableColumnSizing.revealOverflow(in: scrollView, afterResizing: [])
        XCTAssertEqual(scrollView.flashes, 0, "an update that resized nothing must not flash")

        TableColumnSizing.revealOverflow(in: scrollView, afterResizing: [0])
        XCTAssertEqual(scrollView.flashes, 1, "a resize that overflows the panel reveals the scroller")

        column.width = 100
        tableView.sizeToFit()
        scrollView.tile()
        TableColumnSizing.revealOverflow(in: scrollView, afterResizing: [0])
        XCTAssertEqual(scrollView.flashes, 1, "a table that fits has nothing to reveal")
    }
}
