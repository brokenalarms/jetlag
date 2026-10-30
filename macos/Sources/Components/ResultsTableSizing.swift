import SwiftUI



/// Assigning a column width invalidates the table's layout, and `updateNSView` fires
/// once per row appended during a streaming run. Writing a width that has not changed
/// would therefore keep the window's update-constraints pass alive for as long as rows
/// keep arriving, which AppKit eventually aborts as a constraint loop.
enum TableColumnSizing {
    /// Assigns each width only where it differs from what the column already resolves
    /// to. The comparison uses the width clamped to the column's own min/max, since
    /// that — not the requested value — is what the column will end up reporting.
    @discardableResult
    static func applyWidths(_ widths: [CGFloat], to tableView: NSTableView) -> [Int] {
        var resized: [Int] = []
        for (index, width) in widths.enumerated() where index < tableView.tableColumns.count {
            let column = tableView.tableColumns[index]
            let target = min(max(width, column.minWidth), column.maxWidth)
            guard column.width != target else { continue }
            column.width = target
            resized.append(index)
        }
        return resized
    }

    /// How close to a column's right edge a click counts as landing on its divider.
    static let dividerHitZone: CGFloat = 5

    /// Snaps the column whose divider the click landed on to its unclamped content-fit
    /// width — the width that shows its widest cell untruncated, past the cap
    /// `applyWidths` holds it to. That cap lives in the measurement only, never as the
    /// column's own `maxWidth`, or AppKit would clamp this width straight back down.
    /// Returns the column it resized, or nil if the click missed every divider.
    @discardableResult
    static func fitColumn(atDividerX x: CGFloat, in tableView: NSTableView,
                          to contentFitWidths: [CGFloat]) -> Int? {
        for index in 0..<min(tableView.numberOfColumns, contentFitWidths.count)
        where abs(x - tableView.rect(ofColumn: index).maxX) < dividerHitZone {
            tableView.tableColumns[index].width = contentFitWidths[index]
            return index
        }
        return nil
    }

    /// The table can be wider than the panel, so it needs a horizontal scroller.
    /// Which style that scroller takes is the user's system preference, not the
    /// app's: forcing the legacy style would override "Show scroll bars" for this one
    /// view. Each flag is compared before assignment because this runs on every
    /// update, and an unconditional write would re-invalidate the scroll view's
    /// layout every pass (jetlag-m9a).
    static func configureHorizontalScroller(for scrollView: NSScrollView) {
        if !scrollView.hasHorizontalScroller {
            scrollView.hasHorizontalScroller = true
        }
        if !scrollView.autohidesScrollers {
            scrollView.autohidesScrollers = true
        }
    }

    /// Overlay scrollers stay hidden until a scroll gesture, so a table that has just
    /// grown past its panel gives no sign that columns lie off to the right. AppKit's
    /// cue for exactly this is `flashScrollers()`, which reveals them briefly — what
    /// Finder does when a view's content changes. Called only when a width actually
    /// changed and the document now overflows, so idle updates never flash.
    static func revealOverflow(in scrollView: NSScrollView, afterResizing resized: [Int]) {
        guard !resized.isEmpty, let document = scrollView.documentView,
              document.frame.width > scrollView.contentView.bounds.width else { return }
        scrollView.flashScrollers()
    }
}

struct ColumnAutoSizer: NSViewRepresentable {
    let widths: ColumnWidths
    /// SwiftUI creates the `Table`'s `NSTableView` lazily and updates a representable
    /// only when its value changes, so widths alone are not enough to reach AppKit: a
    /// run over uniformly named files computes the same widths every time, and the
    /// coordinator would never get an update in which the table exists to be found.
    /// The row count changes on every append, which is exactly when it must look.
    let rowCount: Int

    final class Coordinator: NSObject {
        weak var tableView: NSTableView?
        var widths = ColumnWidths()
        var gestureInstalled = false
        var tailFollower: TableTailFollower?

        @objc func headerDoubleClicked(_ gesture: NSClickGestureRecognizer) {
            guard let headerView = gesture.view as? NSTableHeaderView,
                  let tableView else { return }

            TableColumnSizing.fitColumn(atDividerX: gesture.location(in: headerView).x,
                                        in: tableView, to: widths.contentFit)
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> NSView {
        NSView(frame: .zero)
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        let coordinator = context.coordinator
        coordinator.widths = widths

        if coordinator.tableView == nil || coordinator.tableView?.window == nil {
            coordinator.tableView = findTableView(from: nsView)
        }

        if let tableView = coordinator.tableView {
            // SwiftUI's Table leaves the NSTableView on uniform autoresizing, which
            // re-fits every column to the panel's width the moment the widths we set
            // overflow it — the columns end up proportionally squeezed, not sized to
            // their content. With autoresizing off the widths stand and the table
            // overflows into its horizontal scroller instead.
            if tableView.columnAutoresizingStyle != .noColumnAutoresizing {
                tableView.columnAutoresizingStyle = .noColumnAutoresizing
            }
            let resized = TableColumnSizing.applyWidths(widths.fitted, to: tableView)
            tableView.enclosingScrollView?.detachSizeFromContent()

            if !coordinator.gestureInstalled, let headerView = tableView.headerView {
                let gesture = NSClickGestureRecognizer(
                    target: coordinator,
                    action: #selector(Coordinator.headerDoubleClicked(_:)))
                gesture.numberOfClicksRequired = 2
                // A click recognizer delays the primary mouse button by default (it
                // reports YES dynamically for its primary-button mask), which holds
                // mouse-downs back from the header until the gesture fails — the
                // divider's resize cursor and drag would then only engage after a
                // first, discarded click. The action fires on the second click either
                // way, so nothing here needs the delay.
                gesture.delaysPrimaryMouseButtonEvents = false
                headerView.addGestureRecognizer(gesture)
                coordinator.gestureInstalled = true
            }

            if let scrollView = tableView.enclosingScrollView {
                // The follower does its own work from AppKit's notifications; nothing
                // here may scroll, because SwiftUI updates the table's rows in this same
                // pass and the before/after ordering is undefined.
                if coordinator.tailFollower?.scrollView !== scrollView {
                    coordinator.tailFollower = TableTailFollower(scrollView: scrollView)
                }
                TableColumnSizing.configureHorizontalScroller(for: scrollView)
                TableColumnSizing.revealOverflow(in: scrollView, afterResizing: resized)
            }
        }
    }

    /// The window holds more than one `NSTableView` — the sidebar `List` is an outline
    /// view, and comes first in the window's subview order — so the search starts at
    /// the nearest ancestor of this view and accepts only a table with this table's
    /// column count.
    private func findTableView(from view: NSView) -> NSTableView? {
        var ancestor = view.superview
        while let candidate = ancestor {
            if let found = searchForTableView(in: candidate) { return found }
            ancestor = candidate.superview
        }
        return nil
    }

    private func searchForTableView(in view: NSView) -> NSTableView? {
        if let tableView = view as? NSTableView, tableView.tableColumns.count == widths.fitted.count {
            return tableView
        }
        for subview in view.subviews {
            if let found = searchForTableView(in: subview) {
                return found
            }
        }
        return nil
    }
}
