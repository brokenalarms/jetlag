import AppKit

/// Whether a scrolled view is parked at its tail, on the log panel's tolerance: the
/// last row counts as visible while its final few points are still clipped, so a table
/// resting a pixel short of the end keeps following.
enum TableTailFollowing {
    static let bottomThreshold: CGFloat = 10

    static func isAtBottom(visibleMaxY: CGFloat, documentHeight: CGFloat) -> Bool {
        visibleMaxY >= documentHeight - bottomThreshold
    }
}

/// Keeps the Files table pinned to its newest row while the user is at the bottom, and
/// leaves the scroll position alone once they have scrolled the last row out of view.
///
/// The log reaches the same behaviour inside its own `updateNSView`, because it owns the
/// text storage and can decide `wasAtBottom` before the document grows. SwiftUI owns the
/// `Table`'s `NSTableView`, so there is no point in the app's code that runs between the
/// rows arriving and the table laying them out — and scrolling from the representable's
/// `updateNSView` would be AppKit layout driven from inside a SwiftUI render pass, the
/// defect `WindowEdgeGrowth` exists to avoid. AppKit posts both halves of the decision
/// as notifications instead: the clip view's bounds move when the user scrolls, and the
/// document view's frame grows when SwiftUI has appended rows.
final class TableTailFollower: NSObject {
    private(set) weak var scrollView: NSScrollView?
    private(set) var followingTail: Bool
    private var documentHeight: CGFloat

    init(scrollView: NSScrollView) {
        self.scrollView = scrollView
        let clipView = scrollView.contentView
        let documentView = scrollView.documentView
        documentHeight = documentView?.frame.height ?? 0
        followingTail = TableTailFollowing.isAtBottom(
            visibleMaxY: clipView.documentVisibleRect.maxY,
            documentHeight: documentHeight)
        super.init()

        clipView.postsBoundsChangedNotifications = true
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(clipViewBoundsChanged),
            name: NSView.boundsDidChangeNotification,
            object: clipView)

        if let documentView {
            documentView.postsFrameChangedNotifications = true
            NotificationCenter.default.addObserver(
                self,
                selector: #selector(documentViewFrameChanged),
                name: NSView.frameDidChangeNotification,
                object: documentView)
        }
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    /// The user scrolling up so the last row leaves the view stops the following;
    /// scrolling back to the bottom starts it again. Our own `scrollRowToVisible` lands
    /// here too, and lands at the bottom, so following survives it.
    @objc private func clipViewBoundsChanged() {
        guard let scrollView, let documentView = scrollView.documentView else { return }
        followingTail = TableTailFollowing.isAtBottom(
            visibleMaxY: scrollView.contentView.documentVisibleRect.maxY,
            documentHeight: documentView.frame.height)
    }

    /// A taller document means SwiftUI has appended rows. Growth alone does not move the
    /// clip view's bounds origin, so it cannot have flipped the following off first.
    @objc private func documentViewFrameChanged() {
        guard let documentView = scrollView?.documentView else { return }
        let grew = documentView.frame.height > documentHeight
        documentHeight = documentView.frame.height
        guard grew, followingTail,
              let tableView = documentView as? NSTableView,
              tableView.numberOfRows > 0 else { return }
        tableView.scrollRowToVisible(tableView.numberOfRows - 1)
    }
}
