import AppKit

/// AppKit views hosted inside the inspector are asked for their layout requirements
/// during the window's update-constraints pass. Anything they answer that depends on
/// their current content — text that just grew, table columns that just widened —
/// reaches `SplitViewChildController` as a changed min size, which re-enqueues the
/// pass; the window aborts once it has run more passes than it has views. The
/// inspector's width comes from `inspectorColumnWidth`, so hosted views must keep
/// their layout contribution constant no matter what they contain.
enum HostedViewSizing {
    /// Below `.defaultLow` on both axes: the hosted view accepts whatever size the
    /// inspector hands it and never argues back from its content.
    static let contentIndifferentPriority = NSLayoutConstraint.Priority(1)
}

/// A scroll view that reports no intrinsic size, so its document view can grow
/// without changing what the hosting view asks of the window.
final class ContentAgnosticScrollView: NSScrollView {
    override var intrinsicContentSize: NSSize {
        NSSize(width: NSView.noIntrinsicMetric, height: NSView.noIntrinsicMetric)
    }
}

extension NSView {
    /// Drops hugging and compression resistance to the floor so layout never derives
    /// this view's size from what it currently holds. Priorities are written only when
    /// they differ, so calling this from `updateNSView` cannot itself invalidate layout.
    func detachSizeFromContent() {
        let priority = HostedViewSizing.contentIndifferentPriority
        for axis in [NSLayoutConstraint.Orientation.horizontal, .vertical] {
            if contentHuggingPriority(for: axis) != priority {
                setContentHuggingPriority(priority, for: axis)
            }
            if contentCompressionResistancePriority(for: axis) != priority {
                setContentCompressionResistancePriority(priority, for: axis)
            }
        }
    }
}
