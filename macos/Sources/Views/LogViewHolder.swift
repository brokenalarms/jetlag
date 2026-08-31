import AppKit

/// The log's live scroll view and how much of the transcript it already shows, owned by
/// the session rather than by the view that displays it.
///
/// The inspector shows the log behind a SwiftUI conditional, so closing the panel tears
/// the representable down. Rebuilt from scratch on the next open, the log would have the
/// whole transcript to re-render and no memory of where the user was reading; holding
/// both here means reopening re-mounts the same view, still scrolled where it was left.
final class LogViewHolder {
    lazy var scrollView = LogScrollView.make()

    /// Tracks how much of the log the text view already shows, so an update appends only
    /// what is new. Rebuilding the whole transcript per line is O(n²) over a run —
    /// thousands of lines — and was what left the app far behind the pipeline.
    var renderedCount = 0
}

/// The log's scroll view: content-agnostic, because log text grows line by line while a
/// run streams and a scroll view that sized itself from its document would report a new
/// min size to the inspector on every appended line.
final class LogScrollView: ContentAgnosticScrollView {
    /// Whether the view still owes a scroll to the end of the transcript. The scroll
    /// cannot always be landed where the decision is made: a panel opening for the first
    /// time is asked to render its lines before it has been laid out, and a view with no
    /// height — or whose text view has not yet grown to its text — has nowhere to scroll
    /// to. The pin stays owed until a scroll actually lands at the end.
    private(set) var pinnedToEnd = false

    /// Says where the view should sit now the transcript has grown: at the end when the
    /// user was parked at the tail, where they already are otherwise.
    func followTail(_ follows: Bool) {
        pinnedToEnd = follows
        scrollToEndIfPinned()
    }

    override func layout() {
        super.layout()
        scrollToEndIfPinned()
    }

    /// The height the transcript needs. The text view's frame catches up to it only when
    /// AppKit next resizes the view, so a scroll taken before that lands short — which is
    /// why the pin is cleared by where the scroll ended up rather than by having tried.
    private var laidOutTextHeight: CGFloat {
        guard let textView = documentView as? NSTextView,
              let container = textView.textContainer,
              let layoutManager = textView.layoutManager else { return 0 }
        layoutManager.ensureLayout(for: container)
        return layoutManager.usedRect(for: container).height
            + textView.textContainerInset.height * 2
    }

    /// Clearing the pin only once it has landed is what keeps a later layout pass — a
    /// window resize, the panel reopening — from yanking a view the user has since
    /// scrolled away from, while still finishing a scroll the view was too small to make.
    private func scrollToEndIfPinned() {
        guard pinnedToEnd, bounds.height > 0,
              let textView = documentView as? NSTextView else { return }
        let contentHeight = max(laidOutTextHeight, textView.frame.height)
        textView.scrollToEndOfDocument(nil)
        pinnedToEnd = !TableTailFollowing.isAtBottom(
            visibleMaxY: contentView.documentVisibleRect.maxY,
            documentHeight: contentHeight)
    }

    /// Built by hand rather than with `NSTextView.scrollableTextView()` so the scroll view
    /// is this subclass and the text view wraps long lines like a terminal.
    static func make() -> LogScrollView {
        let scrollView = LogScrollView()
        scrollView.borderType = .noBorder
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.drawsBackground = false
        scrollView.detachSizeFromContent()

        let textView = NSTextView(frame: NSRect(origin: .zero, size: scrollView.contentSize))
        textView.minSize = NSSize(width: 0, height: 0)
        textView.maxSize = NSSize(
            width: CGFloat.greatestFiniteMagnitude,
            height: CGFloat.greatestFiniteMagnitude)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.textContainer?.widthTracksTextView = true
        textView.textContainer?.containerSize = NSSize(
            width: scrollView.contentSize.width,
            height: CGFloat.greatestFiniteMagnitude)

        textView.isEditable = false
        textView.isSelectable = true
        textView.font = LogTextView.font
        textView.textColor = .labelColor
        textView.backgroundColor = .clear
        textView.textContainerInset = NSSize(width: 10, height: 6)
        textView.autoresizingMask = [.width]

        scrollView.documentView = textView
        return scrollView
    }
}
