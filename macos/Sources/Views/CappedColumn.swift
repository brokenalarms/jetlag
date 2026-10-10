import AppKit
import SwiftUI

/// A vertical stack exactly as tall as its content, up to `maxHeight`. Past that, the
/// subview with a lower `layoutPriority` than its siblings — a scroll view — gives up the
/// difference. The height it is offered is ignored, so under
/// `windowResizability(.contentSize)` the window follows the content as it grows and
/// shrinks, but never past the limit.
struct CappedColumn: Layout {
    var maxHeight: CGFloat

    static func heights(natural: [CGFloat], yielding: Int?, maxHeight: CGFloat) -> [CGFloat] {
        var heights = natural
        let overflow = natural.reduce(0, +) - maxHeight
        guard overflow > 0, let yielding else { return heights }
        heights[yielding] = max(0, heights[yielding] - overflow)
        return heights
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? subviews.map { $0.sizeThatFits(.unspecified).width }.max() ?? 0
        return CGSize(width: width, height: heights(width: width, subviews: subviews).reduce(0, +))
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for (subview, height) in zip(subviews, heights(width: bounds.width, subviews: subviews)) {
            subview.place(
                at: CGPoint(x: bounds.minX, y: y),
                anchor: .topLeading,
                proposal: ProposedViewSize(width: bounds.width, height: height))
            y += height
        }
    }

    private func heights(width: CGFloat, subviews: Subviews) -> [CGFloat] {
        let natural = subviews.map { $0.sizeThatFits(ProposedViewSize(width: width, height: nil)).height }
        let priorities = subviews.map(\.priority)
        let yielding = priorities.min().flatMap { lowest in
            lowest < (priorities.max() ?? lowest) ? priorities.firstIndex(of: lowest) : nil
        }
        return Self.heights(natural: natural, yielding: yielding, maxHeight: maxHeight)
    }
}

/// Reports the tallest the window's content can be with the whole window inside its
/// screen's visible frame — clear of the menu bar and the Dock. Content of a fixed
/// height would otherwise size the window past the bottom of the screen, where its
/// lower edge can be neither seen nor dragged.
struct WindowContentHeightLimitReader: NSViewRepresentable {
    var onChange: (CGFloat) -> Void

    static func limit(visibleScreenHeight: CGFloat, windowHeight: CGFloat, contentHeight: CGFloat) -> CGFloat {
        visibleScreenHeight - (windowHeight - contentHeight)
    }

    func makeNSView(context: Context) -> ReportingView {
        ReportingView()
    }

    func updateNSView(_ view: ReportingView, context: Context) {
        view.onChange = onChange
    }

    final class ReportingView: NSView {
        var onChange: ((CGFloat) -> Void)?
        private var observers: [NSObjectProtocol] = []

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            observers.forEach(NotificationCenter.default.removeObserver)
            observers = []
            guard let window else { return }
            let center = NotificationCenter.default
            let reportOnChange: (Notification) -> Void = { [weak self] _ in
                MainActor.assumeIsolated { self?.report() }
            }
            observers = [
                center.addObserver(forName: NSWindow.didChangeScreenNotification, object: window, queue: .main, using: reportOnChange),
                center.addObserver(forName: NSApplication.didChangeScreenParametersNotification, object: nil, queue: .main, using: reportOnChange),
            ]
            report()
        }

        private func report() {
            guard let window, let screen = window.screen else { return }
            onChange?(WindowContentHeightLimitReader.limit(
                visibleScreenHeight: screen.visibleFrame.height,
                windowHeight: window.frame.height,
                contentHeight: window.contentLayoutRect.height))
        }
    }
}
